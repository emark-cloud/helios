"""On-chain log watcher feeding the Sentinel activity rail.

The decision loop in `helios_allocator.runtime.loop` only emits events
when *it* takes an action — it never observes the chain directly. That
left two visible gaps:

  1. `scripts/e2e-scenario.sh` drives `AllocatorVault` directly without
     going through Sentinel, so the dashboard rail stayed blank during
     a judge demo even when capital moved on chain.
  2. The permissionless defund flow (`triggerDefund` → `DefundObserved`
     → `DefundFinalized`) is initiated by anyone, not by Sentinel —
     the loop never sees those state transitions.

`ChainWatcher` polls `eth_getLogs` against the configured RPC and the
addresses in `contracts/deployments/<chain>.json`, decodes the logs via
the IAllocatorVault / IStrategyVault ABIs, and translates each
relevant log into an `AllocatorEvent` posted to `AllocatorStore`. The
store's `(tx_hash, kind, strategy_id)` dedup ring then de-duplicates
against the loop's own emits, so the rail shows one entry per logical
action regardless of which side observed it first.

Stub mode: if `rpc_url` is empty the watcher is a no-op (mirrors
`AllocatorOnChain`'s posture). Tests use that mode plus direct calls
into `_handle_logs` to avoid spinning up an RPC client.

Helios.md §11.3 (allocator event surface), Phase 4 plan §4.3 (WS-SVC-1).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from helios_allocator.runtime import AllocatorEvent, AllocatorStore
from helios_allocator.runtime.state import EventKind
from helios_contracts_abi.abis import IAllocatorVault_ABI, IStrategyVault_ABI
from web3 import Web3

_log = structlog.get_logger(__name__)

# eth_getLogs window. Larger windows reduce RPC pressure but lose
# resolution if a watcher restart needs to re-scan; 2_048 covers
# ~10 minutes of Kite blocks (~3s block time) so a routine restart
# replays in one batch and still fits comfortably under the 10k cap
# enforced by most public RPCs.
_MAX_LOGS_RANGE = 2_048

# Maximum forward leap per tick when the chain runs faster than the
# poll cadence (e.g. an indexer was paused for a while). Without this
# the first tick after a long pause attempts a single eth_getLogs over
# tens of thousands of blocks and trips the RPC's range cap.
_MAX_CATCHUP_BLOCKS = 50_000

# Default checkpoint persistence interval — write to disk every N
# successful ticks rather than every tick to keep the watcher's cadence
# decoupled from a slow filesystem.
_CHECKPOINT_FLUSH_EVERY = 4


# ── Address sets ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WatchAddresses:
    """Resolved addresses the watcher subscribes to.

    `allocator_vault` is the single AllocatorVault instance whose
    user-scoped events drive the dashboard's per-user rail.
    `strategy_vaults` is the set of StrategyVault proxies; their
    NAV-divergence observations fan out to any user with a live
    allocation in the corresponding strategy.
    """

    allocator_vault: str
    strategy_vaults: tuple[str, ...]

    @classmethod
    def from_deployments(cls, addresses: dict[str, str]) -> WatchAddresses:
        """Build from a `contracts/deployments/<chain>.json` `addresses` map.

        Picks every address whose key starts with `strategyVault` —
        covers the base trio plus the Variant2/Variant3 proxies that
        Phase-3 redeploy added (see CLAUDE.md "Key addresses").
        """
        allocator = addresses.get("allocatorVault", "")
        strategies = tuple(
            sorted(
                Web3.to_checksum_address(v)
                for k, v in addresses.items()
                if k.startswith("strategyVault") and v
            )
        )
        return cls(
            allocator_vault=Web3.to_checksum_address(allocator) if allocator else "",
            strategy_vaults=strategies,
        )


# ── Config ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ChainWatchConfig:
    rpc_url: str
    chain_id: int
    addresses: WatchAddresses
    # Polling cadence. Kite testnet's block time is ~3s; matching that
    # keeps the rail near-realtime without burning RPC quota. Tests
    # override to 0 and drive `tick_once` manually.
    poll_interval_sec: float = 3.0
    # Initial-block resolution: when no checkpoint exists, start from
    # the latest block (avoid replaying historical capital movements
    # the dashboard already reflects via the loop's mirror reads).
    start_at_latest_when_unset: bool = True
    # Optional path on disk for the checkpoint file. If None, the
    # watcher persists only in memory and re-scans `latest` on restart.
    checkpoint_path: Path | None = None


# ── Event topic table ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _EventBinding:
    """One ABI event the watcher decodes."""

    name: str
    signature: str  # canonical e.g. "AllocationCreated(address,address,uint256,uint32)"
    contract: str  # "allocatorVault" or "strategyVault"


def _abi_canonical(item: dict[str, Any]) -> str:
    types = ",".join(_canonical_input_type(i) for i in item.get("inputs", []))
    return f"{item['name']}({types})"


def _canonical_input_type(inp: dict[str, Any]) -> str:
    t = inp["type"]
    if t.startswith("tuple"):
        inner = ",".join(_canonical_input_type(c) for c in inp.get("components", []))
        return f"({inner}){t[len('tuple') :]}"
    return t


def _build_topic_table(
    bindings: Sequence[_EventBinding],
) -> dict[bytes, _EventBinding]:
    table: dict[bytes, _EventBinding] = {}
    for b in bindings:
        topic = bytes(Web3.keccak(text=b.signature))
        table[topic] = b
    return table


_WATCHED_EVENTS: tuple[str, ...] = (
    # AllocatorVault — user-scoped, route directly via indexed `user` topic.
    "AllocationCreated",
    "AllocationIncreased",
    "AllocationDecreased",
    "StrategyDefunded",
    "StrategyFeeSettled",
    "DefundObserved",
    "DefundArmed",
    "DefundCancelled",
    "DefundFinalized",
    # StrategyVault — strategy-scoped, fan out to users with a live alloc.
    "NavDivergenceObserved",
)


def _build_bindings() -> list[_EventBinding]:
    out: list[_EventBinding] = []
    for item in IAllocatorVault_ABI:
        if item.get("type") == "event" and item["name"] in _WATCHED_EVENTS:
            out.append(
                _EventBinding(
                    name=item["name"],
                    signature=_abi_canonical(item),
                    contract="allocatorVault",
                )
            )
    for item in IStrategyVault_ABI:
        if item.get("type") == "event" and item["name"] in _WATCHED_EVENTS:
            out.append(
                _EventBinding(
                    name=item["name"],
                    signature=_abi_canonical(item),
                    contract="strategyVault",
                )
            )
    return out


# ── Watcher ──────────────────────────────────────────────────────────


@dataclass
class _Checkpoint:
    """In-memory checkpoint state, optionally mirrored to disk."""

    last_scanned_block: int = 0
    flushed: int = 0  # number of ticks since last disk flush

    def to_json(self) -> str:
        return json.dumps({"last_scanned_block": self.last_scanned_block})

    @classmethod
    def from_path(cls, path: Path) -> _Checkpoint:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls(last_scanned_block=int(data.get("last_scanned_block", 0)))
        except (OSError, ValueError, json.JSONDecodeError):
            return cls()


class ChainWatcher:
    """Polls `eth_getLogs` and forwards decoded events to AllocatorStore.

    Composition mirrors `AllocatorLoop`:
      * `start()` / `stop()` lifecycle managed by the FastAPI app's
        lifespan context.
      * `tick_once()` is the unit-testable body — tests drive it
        directly without start/stop or sleeping.
    """

    def __init__(
        self,
        store: AllocatorStore,
        config: ChainWatchConfig,
        web3_factory: Callable[[], Web3] | None = None,
    ) -> None:
        self._store = store
        self._cfg = config
        self._bindings = _build_bindings()
        self._topics = _build_topic_table(self._bindings)
        self._allocator_vault_lc = config.addresses.allocator_vault.lower()
        self._strategy_vaults_lc = {a.lower() for a in config.addresses.strategy_vaults}
        self._live = bool(
            config.rpc_url and config.addresses.allocator_vault and config.chain_id > 0
        )
        # Lazy Web3 init — same posture as AllocatorOnChain so dry-run
        # tests don't dial the RPC.
        self._w3_factory = web3_factory or (
            (lambda: Web3(Web3.HTTPProvider(config.rpc_url))) if self._live else None
        )
        self._w3: Web3 | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._checkpoint = (
            _Checkpoint.from_path(config.checkpoint_path)
            if config.checkpoint_path is not None
            else _Checkpoint()
        )

    # ── Lifecycle ─────────────────────────────────────────────────
    @property
    def live(self) -> bool:
        return self._live

    @property
    def last_scanned_block(self) -> int:
        return self._checkpoint.last_scanned_block

    def start(self) -> None:
        if self._task is not None or not self._live:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="sentinel.chain_watch")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick_once()
            except Exception as exc:  # pragma: no cover — defensive
                _log.warning("chain_watch.tick_failed", err=str(exc), exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._cfg.poll_interval_sec)
            except TimeoutError:
                continue

    # ── Tick ──────────────────────────────────────────────────────
    async def tick_once(self) -> int:
        """Scan a single window and return the count of emitted events.

        Off-thread Web3 calls keep the FastAPI event loop draining
        even when an RPC stalls — same posture as AllocatorOnChain.
        """
        if not self._live:
            return 0
        w3 = self._ensure_w3()
        latest = await asyncio.to_thread(lambda: w3.eth.block_number)
        cp = self._checkpoint
        if cp.last_scanned_block == 0:
            cp.last_scanned_block = int(latest) if self._cfg.start_at_latest_when_unset else 0
            return 0
        from_block = cp.last_scanned_block + 1
        to_block = min(int(latest), from_block + _MAX_CATCHUP_BLOCKS - 1)
        if to_block < from_block:
            return 0

        emitted = 0
        cursor = from_block
        addresses = [
            Web3.to_checksum_address(a)
            for a in (
                self._cfg.addresses.allocator_vault,
                *self._cfg.addresses.strategy_vaults,
            )
            if a
        ]
        while cursor <= to_block:
            window_end = min(cursor + _MAX_LOGS_RANGE - 1, to_block)
            logs = await asyncio.to_thread(
                lambda c=cursor, e=window_end: w3.eth.get_logs(  # type: ignore[arg-type]
                    {"fromBlock": c, "toBlock": e, "address": addresses}
                )
            )
            emitted += self._handle_logs(logs)
            cursor = window_end + 1

        cp.last_scanned_block = to_block
        cp.flushed += 1
        if self._cfg.checkpoint_path is not None and cp.flushed >= _CHECKPOINT_FLUSH_EVERY:
            self._flush_checkpoint()
        return emitted

    def _ensure_w3(self) -> Web3:
        w3 = self._w3
        if w3 is None:
            assert self._w3_factory is not None
            w3 = self._w3_factory()
            self._w3 = w3
        return w3

    def _flush_checkpoint(self) -> None:
        path = self._cfg.checkpoint_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._checkpoint.to_json())
        self._checkpoint.flushed = 0

    # ── Decode + emit ─────────────────────────────────────────────
    def _handle_logs(self, logs: Iterable[Any]) -> int:
        emitted = 0
        for log in logs:
            try:
                if self._dispatch(log):
                    emitted += 1
            except Exception as exc:  # pragma: no cover — defensive
                _log.warning(
                    "chain_watch.decode_failed",
                    err=str(exc),
                    tx_hash=_log_attr(log, "transactionHash", "").hex()
                    if hasattr(_log_attr(log, "transactionHash", ""), "hex")
                    else "",
                )
        return emitted

    def _dispatch(self, log: Any) -> bool:
        topics = _log_attr(log, "topics", ()) or ()
        if not topics:
            return False
        sig = _topic_bytes(topics[0])
        binding = self._topics.get(sig)
        if binding is None:
            return False
        contract_lc = _log_attr(log, "address", "").lower()
        if binding.contract == "allocatorVault" and contract_lc != self._allocator_vault_lc:
            return False
        if binding.contract == "strategyVault" and contract_lc not in self._strategy_vaults_lc:
            return False
        decoded = self._decode(binding, log)
        if decoded is None:
            return False
        return self._emit_decoded(binding, decoded)

    def _decode(self, binding: _EventBinding, log: Any) -> dict[str, Any] | None:
        w3 = self._ensure_w3()
        # The web3 contract object exposes a per-event decoder accessed
        # via `events.<Name>().process_log(log)` returning an
        # AttributeDict with `args`, `transactionHash`, `logIndex`. The
        # contract instance is cheap so we build it once per binding.
        abi = IAllocatorVault_ABI if binding.contract == "allocatorVault" else IStrategyVault_ABI
        contract_addr = (
            self._cfg.addresses.allocator_vault
            if binding.contract == "allocatorVault"
            else _log_attr(log, "address", "")
        )
        try:
            contract = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=abi)
            event_obj = contract.events[binding.name]()
            return event_obj.process_log(log)
        except Exception as exc:  # pragma: no cover — defensive
            _log.warning(
                "chain_watch.process_log_failed",
                event=binding.name,
                err=str(exc),
            )
            return None

    # ── Emit handlers ─────────────────────────────────────────────
    def _emit_decoded(self, binding: _EventBinding, decoded: dict[str, Any]) -> bool:
        args = dict(decoded["args"])
        tx_hash = _hex(decoded.get("transactionHash"))
        ts = int(time.time())
        name = binding.name
        if name == "AllocationCreated":
            return self._emit_user(
                args["user"],
                kind="ALLOCATION_CREATED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=int(args["amount"]),
                reason="ON_CHAIN",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "AllocationIncreased":
            return self._emit_user(
                args["user"],
                kind="ALLOCATION_INCREASED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=int(args["delta"]),
                reason="ON_CHAIN",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "AllocationDecreased":
            return self._emit_user(
                args["user"],
                kind="ALLOCATION_DECREASED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=int(args["delta"]),
                reason="ON_CHAIN",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "StrategyDefunded":
            return self._emit_user(
                args["user"],
                kind="STRATEGY_DEFUNDED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=0,
                reason=str(args.get("reason", "")) or "ON_CHAIN",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "StrategyFeeSettled":
            return self._emit_user(
                args["user"],
                kind="FEE_SETTLED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=int(args.get("feeAmount", 0)),
                reason="ON_CHAIN",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "DefundObserved":
            breach = int(args.get("breachCount", 0))
            return self._emit_user(
                args["user"],
                kind="DEFUND_TRIGGERED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=int(args.get("observedDrawdownBps", 0)),
                reason=f"BREACH_{breach}",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "DefundArmed":
            return self._emit_user(
                args["user"],
                kind="DEFUND_ARMED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=0,
                reason=f"ARMED_AT_BLOCK_{int(args.get('armedAtBlock', 0))}",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "DefundCancelled":
            return self._emit_user(
                args["user"],
                kind="DEFUND_CANCELLED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=0,
                reason=_decode_cancel_reason(args.get("reason")),
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "DefundFinalized":
            slashed = int(args.get("slashedToUser", 0))
            return self._emit_user(
                args["user"],
                kind="DEFUND_FINALIZED",
                strategy_id=_addr(args["strategy"]),
                amount_usd=int(args.get("reward", 0)),
                reason="SLASHED_TO_USER" if slashed > 0 else "REFUNDED",
                ts=ts,
                tx_hash=tx_hash,
            )
        if name == "NavDivergenceObserved":
            return self._fanout_strategy(
                strategy=_addr(args["strategy"]),
                kind="NAV_DIVERGENCE",
                amount_usd=int(args.get("signedNAV", 0)),
                reason=f"FLOOR_{int(args.get('markedFloor', 0))}",
                ts=ts,
                tx_hash=tx_hash,
            )
        return False

    def _emit_user(
        self,
        user: str,
        *,
        kind: EventKind,
        strategy_id: str | None,
        amount_usd: int,
        reason: str,
        ts: int,
        tx_hash: str,
    ) -> bool:
        addr = _addr(user)
        if self._store.get_user(addr) is None:
            return False
        self._store.emit_event(
            AllocatorEvent(
                user_address=addr,
                kind=kind,
                strategy_id=strategy_id,
                amount_usd=amount_usd,
                reason=reason,
                timestamp=ts,
                tx_hash=tx_hash,
            )
        )
        return True

    def _fanout_strategy(
        self,
        *,
        strategy: str,
        kind: EventKind,
        amount_usd: int,
        reason: str,
        ts: int,
        tx_hash: str,
    ) -> bool:
        emitted = False
        for user in self._store.all_users():
            alloc = user.allocations.get(strategy)
            if alloc is None or alloc.defunded:
                continue
            self._store.emit_event(
                AllocatorEvent(
                    user_address=user.meta.user_address,
                    kind=kind,
                    strategy_id=strategy,
                    amount_usd=amount_usd,
                    reason=reason,
                    timestamp=ts,
                    tx_hash=tx_hash,
                )
            )
            emitted = True
        return emitted


# ── Helpers ──────────────────────────────────────────────────────────


def _addr(value: Any) -> str:
    return str(value).lower()


def _hex(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "hex"):
        return "0x" + value.hex().removeprefix("0x")
    s = str(value)
    return s if s.startswith("0x") else f"0x{s}"


def _topic_bytes(topic: Any) -> bytes:
    if isinstance(topic, bytes):
        return topic
    s = str(topic)
    if s.startswith("0x"):
        s = s[2:]
    return bytes.fromhex(s)


def _log_attr(log: Any, name: str, default: Any) -> Any:
    if isinstance(log, dict):
        return log.get(name, default)
    return getattr(log, name, default)


_CANCEL_REASON_RECOVERED = bytes(Web3.keccak(text="RECOVERED"))
_CANCEL_REASON_OPERATOR = bytes(Web3.keccak(text="OPERATOR_CANCEL"))


def _decode_cancel_reason(value: Any) -> str:
    raw = _topic_bytes(value) if value is not None else b""
    if raw == _CANCEL_REASON_RECOVERED:
        return "RECOVERED"
    if raw == _CANCEL_REASON_OPERATOR:
        return "OPERATOR_CANCEL"
    return f"0x{raw.hex()}"


__all__ = [
    "ChainWatchConfig",
    "ChainWatcher",
    "WatchAddresses",
]
