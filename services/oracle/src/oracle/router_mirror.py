"""Mirror signed oracle prices into `MockSwapRouter.setPrice` so on-chain
swaps execute at live market mid (with a configurable bps spread).

Wires into the existing `Poller.on_snapshot` callback so every fresh
snapshot ticks the router for both directions of every (stable, asset)
pair the keeper is configured for. Submission reuses the same Web3 +
eth_account plumbing as `AnchorPoster`: synchronous `post` (used by
tests + CLI), async `post_async` (used in production from the FastAPI
event loop) that runs the blocking Web3 call on a worker thread.

Address-gated like `AnchorPoster`: when RPC URL, signer key, or router
address are unset, the keeper records pending updates without
submitting. Lets the rest of the oracle service boot in dev without
needing live router credentials.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from _template.web3_consts import RECEIPT_TIMEOUT_SEC
from eth_account import Account
from web3 import Web3
from web3.types import TxReceipt

from oracle.router_mirror_math import DEFAULT_SPREAD_BPS, compute_price_pair
from oracle.state import SnapshotStore

# Minimal MockSwapRouter ABI inlined: it's a test-only contract so the
# canonical contracts-abi-py package skips it. We only need `setPrice`,
# `priceOf`, and `decimals()` on ERC20s for sanity reads — small enough
# to keep here rather than ship a dedicated module.
MOCK_SWAP_ROUTER_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "setPrice",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "tokenIn", "type": "address"},
            {"name": "tokenOut", "type": "address"},
            {"name": "num", "type": "uint256"},
            {"name": "denom", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "priceOf",
        "stateMutability": "view",
        "inputs": [
            {"name": "tokenIn", "type": "address"},
            {"name": "tokenOut", "type": "address"},
        ],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "num", "type": "uint256"},
                    {"name": "denom", "type": "uint256"},
                ],
            }
        ],
    },
]

ERC20_DECIMALS_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "decimals",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    }
]

# Bound the audit ring at the same cap as `AnchorPoster.pending` so the
# /v1/audit surface keeps a comparable history (~2-3 days at 60s bars).
_PENDING_RING_CAP = 4096

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PairSpec:
    """One (stable, asset) pair the keeper mirrors. `oracle_asset` is the
    string the oracle store keys snapshots by (e.g. "ETH/USDT"); the
    pair always quotes USD per asset so the converter can use a single
    code path for all assets.
    """

    oracle_asset: str
    stable_address: str
    stable_decimals: int
    asset_address: str
    asset_decimals: int


@dataclass(slots=True)
class MirrorRecord:
    """One audit-ring entry per snapshot tick. Both directions land in a
    single record because they share `price_e18` + `timestamp_ms`."""

    oracle_asset: str
    price_e18: int
    timestamp_ms: int
    s2a_num: int
    s2a_denom: int
    a2s_num: int
    a2s_denom: int
    tx_hashes: tuple[str, str] = ("", "")
    submitted: bool = False
    error: str = ""


@dataclass
class RouterPriceMirror:
    """Live submitter that translates oracle snapshots into router prices.

    Construct with the snapshot store + the list of pairs to mirror.
    Register the keeper as the (or one of the) `Poller.on_snapshot`
    consumer(s) — see `service.py` for the fan-out wiring.
    """

    store: SnapshotStore
    rpc_url: str
    signer_pk: str
    router_address: str
    chain_id: int
    pairs: list[PairSpec]
    spread_bps: int = DEFAULT_SPREAD_BPS
    # Gas: gate the per-bar keeper behind a GLOBAL liveness heartbeat.
    # None/0 → legacy unconditional per-bar posting (zero-behaviour-change
    # rollback). Positive → suppress per-bar posts while a *submitted*
    # setPrice landed within this many seconds. There is no on-chain
    # freshness ceiling (the router has no staleness gate; contrast the
    # oracle anchor's ≤165s cap) — every real trade independently
    # force-refreshes its own asset via `force_refresh_async`.
    liveness_sec: int | None = None
    # Injected for deterministic tests. `monotonic` (not wall-clock) so
    # NTP steps can't move the gate backward/forward — mirrors
    # `PriceAnchorScheduler.clock`.
    clock: Callable[[], float] = time.monotonic

    pending: deque[MirrorRecord] = field(default_factory=lambda: deque(maxlen=_PENDING_RING_CAP))
    _w3: Any = field(default=None, init=False, repr=False)
    _account: Any = field(default=None, init=False, repr=False)
    _contract: Any = field(default=None, init=False, repr=False)
    _by_asset: dict[str, PairSpec] = field(default_factory=dict, init=False, repr=False)
    # Global wall-position (ms) of the last *submitted* setPrice (any
    # asset). None until the first mined post. Advances only on
    # `record.submitted`, mirroring the oracle anchor's
    # `_last_any_commit_ms`. In-memory only: a restart empties it so the
    # first bar after a deploy re-prices, then the gate resumes — same
    # desirable cold-start coverage as the reputation dedup cache.
    _last_submitted_ms: int | None = field(default=None, init=False, repr=False)
    _posts: int = field(default=0, init=False, repr=False)
    _skipped: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        # Index pairs by oracle asset so on_snapshot can look up in O(1).
        # If two pairs ever shared an asset, the latter wins — keep the
        # config simple and assume a single (stable, asset) pair per
        # oracle key.
        self._by_asset = {p.oracle_asset: p for p in self.pairs}

    @property
    def live(self) -> bool:
        return bool(self.rpc_url and self.signer_pk and self.router_address)

    @property
    def posts(self) -> int:
        """Count of genuinely submitted setPrice ticks (per-bar + forced)."""
        return self._posts

    @property
    def skipped(self) -> int:
        """Count of per-bar ticks suppressed by the liveness gate."""
        return self._skipped

    def _gate(self) -> bool:
        """Whether the per-bar keeper should post this tick.

        Liveness mode (`liveness_sec` set, > 0): a single GLOBAL time
        gate — suppress while a *submitted* setPrice landed within the
        window. The sequential Poller fan-out (`_compose_on_snapshot`
        awaits one asset fully before the next) means the first asset
        past the gate posts, `_mark` arms the global clock, and the
        remaining assets in the same tick are suppressed — exactly one
        heartbeat post per `liveness_sec`. Every real trade independently
        force-refreshes its own asset via `force_refresh_async`, so the
        heartbeat is only a cold-start / cosmetic backstop and a global
        clock is strictly the cheaper choice (mirrors the oracle anchor
        `_gate`, global for the same reason).

        Legacy (`liveness_sec` None or 0): unconditional per-bar posting,
        byte-for-byte the pre-gate behaviour (zero-behaviour-change
        rollback).
        """
        if not self.liveness_sec:  # None or 0 → legacy unconditional
            return True
        return not (
            self._last_submitted_ms is not None
            and int(self.clock() * 1000) - self._last_submitted_ms < self.liveness_sec * 1000
        )

    def _mark(self, record: MirrorRecord) -> None:
        """Arm the global liveness clock + bump the post counter — but
        ONLY on a genuinely submitted tx. Dry-run (`not self.live`) and
        failed submits leave the clock untouched so the next bar retries
        (mirrors the oracle anchor `_mark_committed` `rec.submitted`
        discipline and the reputation engine `_arm_if_submitted`)."""
        if record.submitted:
            self._last_submitted_ms = int(self.clock() * 1000)
            self._posts += 1

    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        pk = self.signer_pk if self.signer_pk.startswith("0x") else "0x" + self.signer_pk
        try:
            self._account = Account.from_key(pk)
        except Exception as exc:  # pragma: no cover — defensive
            raise RuntimeError(f"invalid ROUTER_MIRROR_SIGNER_PK: {type(exc).__name__}") from None
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self.router_address),
            abi=MOCK_SWAP_ROUTER_ABI,
        )

    def on_snapshot(self, asset: str) -> MirrorRecord | None:
        """Synchronous per-bar entry point — convenient for tests and
        one-shot replays. Production paths should use `on_snapshot_async`.
        Gated: when the liveness heartbeat is armed this is a no-op."""
        prepped = self._prepare(asset)
        if prepped is None:
            return None
        if not self._gate():
            self._skipped += 1
            return None
        spec, snap, s2a, a2s = prepped
        return self._submit_sync(spec, snap, s2a, a2s)

    async def on_snapshot_async(self, asset: str) -> MirrorRecord | None:
        """Async per-bar entry point. Used in production from the `Poller`
        on_snapshot fan-out — the blocking Web3 path runs on a worker
        thread so the event loop stays free for FastAPI / Poller. Gated:
        when the liveness heartbeat is armed this is a no-op."""
        prepped = self._prepare(asset)
        if prepped is None:
            return None
        if not self._gate():
            self._skipped += 1
            return None
        spec, snap, s2a, a2s = prepped
        return await asyncio.to_thread(self._submit_sync, spec, snap, s2a, a2s)

    def force_refresh(self, asset: str) -> MirrorRecord | None:
        """Post `asset` NOW, bypassing the liveness gate. Sync twin of
        `force_refresh_async` for tests/CLI symmetry with the anchor's
        `force_commit`."""
        prepped = self._prepare(asset)
        if prepped is None:
            return None
        spec, snap, s2a, a2s = prepped
        return self._submit_sync(spec, snap, s2a, a2s)

    async def force_refresh_async(self, asset: str) -> MirrorRecord | None:
        """Post `asset` NOW, bypassing the liveness gate. Backs the
        on-demand `/v1/anchor/commit` seam so the router price is
        force-fresh at trade time. Arms the global clock on submit so the
        next idle per-bar tick is suppressed. Mirrors the oracle
        scheduler's `force_commit_async`."""
        prepped = self._prepare(asset)
        if prepped is None:
            return None
        spec, snap, s2a, a2s = prepped
        return await asyncio.to_thread(self._submit_sync, spec, snap, s2a, a2s)

    def _prepare(self, asset: str) -> tuple[PairSpec, Any, tuple[int, int], tuple[int, int]] | None:
        spec = self._by_asset.get(asset)
        if spec is None:
            return None
        snaps = self.store.recent(asset, 1)
        if not snaps:
            return None
        snap = snaps[0]
        try:
            s2a, a2s = compute_price_pair(
                price_e18=snap.price_e18,
                decimals_stable=spec.stable_decimals,
                decimals_asset=spec.asset_decimals,
                spread_bps=self.spread_bps,
            )
        except ValueError as exc:
            _log.warning(
                "oracle.router_mirror.bad_price",
                asset=asset,
                price_e18=snap.price_e18,
                err=str(exc),
            )
            return None
        return spec, snap, s2a, a2s

    def _submit_sync(
        self,
        spec: PairSpec,
        snap: Any,
        s2a: tuple[int, int],
        a2s: tuple[int, int],
    ) -> MirrorRecord:
        record = MirrorRecord(
            oracle_asset=spec.oracle_asset,
            price_e18=snap.price_e18,
            timestamp_ms=snap.timestamp_ms,
            s2a_num=s2a[0],
            s2a_denom=s2a[1],
            a2s_num=a2s[0],
            a2s_denom=a2s[1],
        )
        if not self.live:
            self.pending.append(record)
            _log.info(
                "oracle.router_mirror.dry_run",
                asset=spec.oracle_asset,
                price_e18=snap.price_e18,
                ts_ms=snap.timestamp_ms,
            )
            return record
        try:
            self._ensure_live()
            tx_s2a = self._set_price(spec.stable_address, spec.asset_address, *s2a)
            tx_a2s = self._set_price(spec.asset_address, spec.stable_address, *a2s)
            record.tx_hashes = (tx_s2a, tx_a2s)
            record.submitted = True
            _log.info(
                "oracle.router_mirror.posted",
                asset=spec.oracle_asset,
                price_e18=snap.price_e18,
                ts_ms=snap.timestamp_ms,
                tx_s2a=tx_s2a,
                tx_a2s=tx_a2s,
            )
        except Exception as exc:
            record.error = str(exc)
            _log.error(
                "oracle.router_mirror.submit_failed",
                asset=spec.oracle_asset,
                err=str(exc),
            )
        # Single arm point for the per-bar + forced live paths. The
        # dry-run path returns above (submitted always False there, so
        # `_mark` would be a no-op anyway); a failed submit reaches here
        # with submitted False ⇒ clock not armed ⇒ next bar retries.
        self._mark(record)
        self.pending.append(record)
        return record

    def _set_price(self, token_in: str, token_out: str, num: int, denom: int) -> str:
        assert self._w3 is not None
        assert self._account is not None
        assert self._contract is not None

        fn = self._contract.functions.setPrice(
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            int(num),
            int(denom),
        )
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
                "chainId": self.chain_id,
                "gasPrice": self._w3.eth.gas_price,
            }
        )
        signed_tx = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"setPrice tx reverted: {tx_hash.hex()}")
        return tx_hash.hex()


__all__ = [
    "MOCK_SWAP_ROUTER_ABI",
    "MirrorRecord",
    "PairSpec",
    "RouterPriceMirror",
]
