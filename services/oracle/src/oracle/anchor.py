"""On-chain `OraclePriceAnchor` / `OracleYieldAnchor` commit task.

The off-chain oracle holds the canonical Poseidon ring root in memory.
Strategy circuits consume this root as a public input — but a circuit
witness is only meaningful if the root has been *committed* on chain by
the registered oracle signer. This module closes that loop:

  1. Build an `OraclePriceCommit` / `OracleYieldCommit` payload for the
     current window: `(root, windowStart, windowEnd, nonce)`.
  2. Sign with `ORACLE_SIGNER_PK` via the same EIP-712 framing the
     contract verifies in `commit(...)` (`HeliosOraclePriceAnchor` /
     `HeliosOracleYieldAnchor`, version "1").
  3. Submit the tx to `OraclePriceAnchor` / `OracleYieldAnchor`.

Address-gated like `services/reputation/anchor.py` and
`services/sentinel/onchain.py`: when the relevant anchor address is
unset (Phase 1 / pre-WS3.B), commits are recorded in `pending` for
test introspection and not submitted.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import structlog
from _template.web3_consts import RECEIPT_TIMEOUT_SEC
from eth_account import Account
from eth_account.messages import encode_typed_data
from helios_contracts_abi.abis import IOracleAnchor_ABI
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxReceipt

from oracle.commit_mirror import CommitMirror
from oracle.state import Snapshot, SnapshotStore
from oracle.yield_state import YieldStore

# `pending` holds one CommitRecord per minute-bar (price) or per
# 5-minute-bar (yield). 4096 keeps roughly 2-3 days of price commits and
# ~14 days of yield commits available for /v1/audit introspection while
# bounding RSS for the always-on schedulers. Older entries fall off
# silently — they're already durable on-chain.
_PENDING_RING_CAP = 4096

_log = structlog.get_logger(__name__)


AnchorKind = Literal["price", "yield"]


_DOMAIN_NAME_PRICE = "HeliosOraclePriceAnchor"
_DOMAIN_NAME_YIELD = "HeliosOracleYieldAnchor"
_DOMAIN_VERSION = "1"
_PRICE_TYPES = {
    "OraclePriceCommit": [
        {"name": "root", "type": "bytes32"},
        {"name": "windowStart", "type": "uint64"},
        {"name": "windowEnd", "type": "uint64"},
        {"name": "nonce", "type": "uint256"},
    ]
}
_YIELD_TYPES = {
    "OracleYieldCommit": [
        {"name": "root", "type": "bytes32"},
        {"name": "windowStart", "type": "uint64"},
        {"name": "windowEnd", "type": "uint64"},
        {"name": "nonce", "type": "uint256"},
    ]
}


def _types_for(kind: AnchorKind) -> dict[str, list[dict[str, str]]]:
    return _PRICE_TYPES if kind == "price" else _YIELD_TYPES


def _domain_name_for(kind: AnchorKind) -> str:
    return _DOMAIN_NAME_PRICE if kind == "price" else _DOMAIN_NAME_YIELD


@dataclass(frozen=True, slots=True)
class CommitPayload:
    kind: AnchorKind
    root: bytes  # 32-byte big-endian Poseidon field element
    window_start: int
    window_end: int
    nonce: int


@dataclass(frozen=True, slots=True)
class SignedCommit:
    payload: CommitPayload
    signature: bytes
    signer: str


def sign_commit(
    payload: CommitPayload,
    private_key_hex: str,
    chain_id: int,
    anchor_address: str,
) -> SignedCommit:
    """Produce an EIP-712 signature consumable by `<Anchor>.commit(...)`.

    Empty `private_key_hex` → returns a 65-byte zero placeholder; useful
    for snapshotting payload shape in unit tests / dry-run mode.
    """
    if not private_key_hex:
        return SignedCommit(payload=payload, signature=b"\x00" * 65, signer="0x" + "0" * 40)
    pk = private_key_hex if private_key_hex.startswith("0x") else "0x" + private_key_hex
    account = Account.from_key(pk)
    domain = {
        "name": _domain_name_for(payload.kind),
        "version": _DOMAIN_VERSION,
        "chainId": chain_id,
        "verifyingContract": anchor_address,
    }
    message = {
        "root": payload.root,
        "windowStart": payload.window_start,
        "windowEnd": payload.window_end,
        "nonce": payload.nonce,
    }
    encoded = encode_typed_data(
        domain_data=domain,
        message_types=_types_for(payload.kind),
        message_data=message,
    )
    signed = account.sign_message(encoded)
    # Annotate the signed-by address; cast handles the `_ in ("upper", "lower")` fork
    # in eth_account address checksumming.
    return SignedCommit(payload=payload, signature=signed.signature, signer=account.address)


@dataclass(slots=True)
class CommitRecord:
    kind: AnchorKind
    root_hex: str
    window_start: int
    window_end: int
    nonce: int
    tx_hash: str = ""
    submitted: bool = False
    error: str = ""


@dataclass
class AnchorPoster:
    """Live on-chain submitter for one anchor (price or yield)."""

    kind: AnchorKind
    rpc_url: str
    signer_pk: str
    anchor_address: str
    chain_id: int

    pending: deque[CommitRecord] = field(default_factory=lambda: deque(maxlen=_PENDING_RING_CAP))
    _w3: Any = field(default=None, init=False, repr=False)
    _account: Any = field(default=None, init=False, repr=False)
    _contract: Any = field(default=None, init=False, repr=False)
    # Serializes nonce-reading + tx-submission per chain. The
    # MultiChainAnchorPoster runs canonical + mirror submits in
    # parallel — that's fine across chains, but the scheduler fires
    # one bar per asset in quick succession (BTC, ETH, SOL → same
    # chain, same EOA). Without the lock, two `get_transaction_count(
    # addr, "pending")` calls inside that gap race and assign the same
    # nonce to two outbound txs, surfacing as `nonce too low: address
    # ... tx: 35 state: 36` or `replacement transaction underpriced`.
    _submit_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def live(self) -> bool:
        return bool(self.rpc_url and self.signer_pk and self.anchor_address)

    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        # Base, Arb-Sepolia, and many testnets use validator metadata in
        # `extraData` that exceeds web3.py's 32-byte default cap. Without
        # the POA-flavoured middleware the strict block-formatter raises
        # `extraData is 86 bytes, but should be 32` on every
        # `get_block(...)` call — which the EIP-1559 fee-detection path
        # in `_gas_params` hits per submit. Injected unconditionally:
        # Kite testnet emits 32-byte extraData and the middleware is a
        # no-op for it, so this is safe to apply to every chain.
        self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        pk = self.signer_pk if self.signer_pk.startswith("0x") else "0x" + self.signer_pk
        try:
            self._account = Account.from_key(pk)
        except Exception as exc:  # pragma: no cover — defensive
            raise RuntimeError(f"invalid ORACLE_SIGNER_PK: {type(exc).__name__}") from None
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self.anchor_address),
            abi=IOracleAnchor_ABI,
        )

    def post(self, payload: CommitPayload) -> CommitRecord:
        """Synchronous submit. Suitable for CLI callers and unit tests.
        Production async paths (`Poller`, `FastAPI`) must use
        `post_async` so the up-to-30s `wait_for_transaction_receipt` does
        not block the event loop.

        Live mode reads the anchor's on-chain `nonce()` and overrides
        `payload.nonce` before signing. The scheduler-tracked nonce is
        only used in dry-run mode (where there is nothing on chain to
        read). Without this override, a process restart or a dropped tx
        permanently desynchronizes the off-chain signing stream from the
        contract's monotonic counter — every subsequent commit then
        reverts with `InvalidSigner`."""
        record = CommitRecord(
            kind=payload.kind,
            root_hex="0x" + payload.root.hex(),
            window_start=payload.window_start,
            window_end=payload.window_end,
            nonce=payload.nonce,
        )
        if not self.live:
            self.pending.append(record)
            _log.info(
                "oracle.anchor.dry_run",
                kind=payload.kind,
                root=record.root_hex,
                window=(payload.window_start, payload.window_end),
                nonce=payload.nonce,
            )
            return record
        try:
            self._ensure_live()
            live_nonce = self._read_onchain_nonce()
            record.nonce = live_nonce
            live_payload = replace(payload, nonce=live_nonce)
            signed = sign_commit(live_payload, self.signer_pk, self.chain_id, self.anchor_address)
            tx_hash, block = self._submit(signed)
            record.tx_hash = tx_hash
            record.submitted = True
            _log.info(
                "oracle.anchor.posted",
                kind=payload.kind,
                root=record.root_hex,
                tx=tx_hash,
                block=block,
                nonce=live_nonce,
            )
        except Exception as exc:
            record.error = str(exc)
            _log.error("oracle.anchor.submit_failed", kind=payload.kind, err=str(exc))
        self.pending.append(record)
        return record

    def _read_onchain_nonce(self) -> int:
        """Fetch the anchor's on-chain monotonic nonce. The contract
        verifies the signed payload against `nonce()` *before*
        incrementing (`OraclePriceAnchor.commit` /
        `OracleYieldAnchor.commit`), so the off-chain signer must always
        sign with the currently-stored value. Read per-commit so a
        restart or a failed tx can't desync the off-chain stream."""
        assert self._contract is not None
        return int(self._contract.functions.nonce().call())

    async def post_async(self, payload: CommitPayload) -> CommitRecord:
        """Async wrapper around `post` — runs the blocking Web3 path
        (`build_transaction` + `wait_for_transaction_receipt`) in a
        worker thread so async callers (oracle `Poller`, FastAPI app)
        don't stall for up to `RECEIPT_TIMEOUT_SEC` per commit."""
        return await asyncio.to_thread(self.post, payload)

    def _submit(self, signed: SignedCommit) -> tuple[str, int]:
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        assert self._contract is not None

        fn = self._contract.functions.commit(
            signed.payload.root,
            int(signed.payload.window_start),
            int(signed.payload.window_end),
            signed.signature,
        )

        # Serialize the read-nonce → sign → send-raw window per chain.
        # The scheduler issues one bar per asset in quick succession,
        # so two `get_transaction_count(addr, "pending")` reads can
        # otherwise return the same value before either tx has hit
        # the mempool, producing duplicate-nonce submits.
        with self._submit_lock:
            gas_params = self._gas_params()
            from_addr = self._account.address
            # Web3.py's auto-estimate underestimates `commit` on Base
            # Sepolia (cold-storage SSTOREs land outside the L2 estimate
            # path), surfacing as `out of gas: gas required exceeds:
            # ~141k` until the signer EOA has warmed every slot it ever
            # touches. Mirror the reputation anchor's 50% headroom — gas
            # is refunded on unused units so there's no real overpay.
            try:
                estimated = fn.estimate_gas({"from": from_addr})
            except Exception:
                estimated = 200_000
            gas_limit = max(int(estimated * 3 // 2), 250_000)
            tx_params: dict[str, Any] = {
                "from": from_addr,
                "nonce": self._w3.eth.get_transaction_count(from_addr, "pending"),
                "chainId": self.chain_id,
                "gas": gas_limit,
                **gas_params,
            }
            tx = fn.build_transaction(tx_params)
            signed_tx = self._account.sign_transaction(tx)
            tx_hash = self._w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        # Receipt-wait is the slow leg (up to RECEIPT_TIMEOUT_SEC); release
        # the lock first so other bars on the same chain can stream txs
        # behind this one (nonce is already committed to the mempool).
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"tx reverted: {tx_hash.hex()}")
        return tx_hash.hex(), int(receipt["blockNumber"])

    def _gas_params(self) -> dict[str, int]:
        """Detect EIP-1559 vs legacy gas pricing per chain. Base + Arb
        reject legacy `gasPrice` if it sits below `baseFeePerGas` —
        which happens routinely when basefee jumps between read and
        submit. Use EIP-1559 with 2× basefee headroom so the tx
        survives one basefee bump, falling back to legacy when the
        chain returns no `baseFeePerGas` (e.g. Kite testnet).
        """
        assert self._w3 is not None
        block = self._w3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas")
        if base_fee:
            priority_fee = self._w3.to_wei(1, "gwei")
            return {
                "maxFeePerGas": int(base_fee) * 2 + priority_fee,
                "maxPriorityFeePerGas": priority_fee,
            }
        return {"gasPrice": self._w3.eth.gas_price}


@dataclass(frozen=True, slots=True)
class _PreparedCommit:
    """Internal: payload plus the side-data needed to update the
    CommitMirror after a successful on-chain submit."""

    payload: CommitPayload
    snapshots_newest_first: list[Snapshot]
    root_int: int
    window_end_ms: int


@dataclass
class PriceAnchorScheduler:
    """Drives `AnchorPoster.post(price)` every N snapshot bars.

    Phase 2 cadence: commit per `interval_bars` bars (default 50) per
    asset. The scheduler keeps a single **global** `_last_window_end_ms`
    because the on-chain `OraclePriceAnchor` enforces a single global
    `windowStart >= _commits[last].windowEnd` chain (no per-asset
    state). With multiple assets sharing one anchor, each new commit —
    regardless of asset — must start at or after the previously
    committed window's end, else the contract reverts
    `NonMonotonicWindow()`.

    Window numbers are bookkeeping only — the contract does NOT bind
    `windowStart`/`windowEnd` to the Poseidon `root`, so it is safe to
    nudge them up to satisfy monotonicity. Strategies prove against
    `root` (verified via `isKnownRoot`) and read `head_timestamp_ms`
    from snapshot data, not from `windowEnd`.

    `mirror`, when provided, is updated after each successful commit
    with the exact `(snapshots, root, window_end)` triple the contract
    received. HTTP handlers serve from the mirror so strategies see the
    same window the anchor verified, eliminating the
    `UnknownOracleRoot()` race between live snapshot state and the
    most-recent committed root.
    """

    store: SnapshotStore
    poster: AnchorPoster
    interval_bars: int = 50
    chain_depth: int = 16  # how many bars feed into the Poseidon root
    mirror: CommitMirror | None = None

    _last_window_end_ms: int = 0
    _bar_counter: dict[str, int] = field(default_factory=dict)
    _nonce: int = 0

    def on_bar(self, asset: str) -> CommitRecord | None:
        """Sync entry point — convenient for tests + scenario replay."""
        prepared = self._prepare(asset)
        if prepared is None:
            return None
        rec = self.poster.post(prepared.payload)
        self._sync_nonce(rec)
        self._record_mirror(asset, rec, prepared)
        return rec

    async def on_bar_async(self, asset: str) -> CommitRecord | None:
        """Async entry point. Used in production from `Poller._on_snapshot`
        so the up-to-30s receipt wait runs on a worker thread, not the
        event loop. Same payload-building semantics as `on_bar`."""
        prepared = self._prepare(asset)
        if prepared is None:
            return None
        rec = await self.poster.post_async(prepared.payload)
        self._sync_nonce(rec)
        self._record_mirror(asset, rec, prepared)
        return rec

    def _sync_nonce(self, rec: CommitRecord) -> None:
        """Re-align the scheduler counter with the on-chain nonce after a
        successful live submit. The poster overrides `payload.nonce`
        with `_read_onchain_nonce()` before signing, so the
        scheduler-local `_nonce` would otherwise drift permanently
        across any dry-run → live transition (or a long dry-run
        rehearsal followed by a real deploy). Without this, subsequent
        dry-run inspection records emit nonces that don't match what
        the contract will accept on the next live submit."""
        if rec.submitted:
            self._nonce = rec.nonce + 1

    def _record_mirror(self, asset: str, rec: CommitRecord, prepared: _PreparedCommit) -> None:
        """Mirror the committed window if (a) we were given a mirror and
        (b) the on-chain submit actually mined. Dry-run posts don't
        write — strategies that read from the mirror should see only
        windows the contract has accepted."""
        if self.mirror is None or not rec.submitted:
            return
        self.mirror.record(
            asset,
            prepared.snapshots_newest_first,
            prepared.root_int,
            prepared.window_end_ms,
        )

    def _prepare(self, asset: str) -> _PreparedCommit | None:
        c = self._bar_counter.get(asset, 0) + 1
        self._bar_counter[asset] = c
        if c < self.interval_bars:
            return None
        self._bar_counter[asset] = 0

        # Atomic `(snaps, root)` — the previous shape called `recent` and
        # `chain_root` as two locked operations and a poller append between
        # them produced a committed root that didn't match the window.
        snaps, root_int = self.store.snapshot_window(asset, self.chain_depth)
        if not snaps:
            return None
        oldest_ts = snaps[-1].timestamp_ms
        newest_ts = snaps[0].timestamp_ms
        # The on-chain anchor's `_commits` array is a single global chain
        # (`windowStart >= _commits[last].windowEnd`), so the off-chain
        # scheduler must track ONE counter across all assets, not one
        # per asset. Bump `window_end` strictly past `window_start` so
        # consecutive same-bar commits (BTC, ETH, SOL, KITE all carrying
        # the same `newest_ts`) get distinct slots in the chain and all
        # land, instead of all but the first reverting `NonMonotonicWindow`.
        window_start = max(oldest_ts, self._last_window_end_ms)
        window_end = max(newest_ts, window_start + 1)

        payload = CommitPayload(
            kind="price",
            root=root_int.to_bytes(32, "big"),
            window_start=window_start,
            window_end=window_end,
            nonce=self._nonce,
        )
        self._nonce += 1
        self._last_window_end_ms = window_end
        return _PreparedCommit(
            payload=payload,
            snapshots_newest_first=snaps,
            root_int=root_int,
            window_end_ms=window_end,
        )


@dataclass
class YieldAnchorScheduler:
    """Same as `PriceAnchorScheduler` but for the yield store."""

    store: YieldStore
    poster: AnchorPoster
    interval_bars: int = 50
    chain_depth: int = 16

    _last_window_end_ms: int = 0
    _bar_counter: dict[str, int] = field(default_factory=dict)
    _nonce: int = 0

    def on_bar(self, market_id: str) -> CommitRecord | None:
        payload = self._prepare(market_id)
        if payload is None:
            return None
        rec = self.poster.post(payload)
        self._sync_nonce(rec)
        return rec

    async def on_bar_async(self, market_id: str) -> CommitRecord | None:
        payload = self._prepare(market_id)
        if payload is None:
            return None
        rec = await self.poster.post_async(payload)
        self._sync_nonce(rec)
        return rec

    def _sync_nonce(self, rec: CommitRecord) -> None:
        """See `PriceAnchorScheduler._sync_nonce` — same rationale."""
        if rec.submitted:
            self._nonce = rec.nonce + 1

    def _prepare(self, market_id: str) -> CommitPayload | None:
        c = self._bar_counter.get(market_id, 0) + 1
        self._bar_counter[market_id] = c
        if c < self.interval_bars:
            return None
        self._bar_counter[market_id] = 0

        snaps, root_int = self.store.snapshot_window(market_id, self.chain_depth)
        if not snaps:
            return None
        oldest_ts = snaps[-1].timestamp_ms
        newest_ts = snaps[0].timestamp_ms
        # Single global counter — see PriceAnchorScheduler._prepare for the
        # reasoning. OracleYieldAnchor enforces the same monotonic check.
        window_start = max(oldest_ts, self._last_window_end_ms)
        window_end = max(newest_ts, window_start + 1)

        payload = CommitPayload(
            kind="yield",
            root=root_int.to_bytes(32, "big"),
            window_start=window_start,
            window_end=window_end,
            nonce=self._nonce,
        )
        self._nonce += 1
        self._last_window_end_ms = window_end
        return payload


@dataclass
class MultiChainAnchorPoster:
    """Fan-out wrapper that submits the same commit payload to one
    canonical anchor (Kite) plus N mirror anchors (Base, Arbitrum) in
    parallel. Each underlying `AnchorPoster` keeps its own per-chain
    nonce — the contract's `nonce()` is read per submit, so the chains
    are allowed to drift relative to each other (one missed commit on
    Arbitrum doesn't poison Kite or Base).

    Implements the same `post` / `post_async` surface as `AnchorPoster`
    so the schedulers can use either type unchanged. Returns the
    canonical chain's `CommitRecord`; per-chain mirror records are
    appended to `mirror_records` for `/v1/audit` introspection. Mirror
    failures are logged but never propagated — execution chains losing
    a commit window is a degraded state, not a halting one.

    phase5-plan.md §WS3.
    """

    canonical: AnchorPoster
    mirrors: list[AnchorPoster] = field(default_factory=list)

    mirror_records: deque[CommitRecord] = field(
        default_factory=lambda: deque(maxlen=_PENDING_RING_CAP)
    )

    @property
    def kind(self) -> AnchorKind:
        return self.canonical.kind

    @property
    def pending(self) -> deque[CommitRecord]:
        # Schedulers / API expose this for /v1/audit; surface canonical's.
        return self.canonical.pending

    @property
    def live(self) -> bool:
        return self.canonical.live

    def post(self, payload: CommitPayload) -> CommitRecord:
        """Synchronous fan-out. Mirrors run sequentially after the canonical
        commit so test ordering is deterministic; production paths
        should use `post_async` for parallelism."""
        canonical_rec = self.canonical.post(payload)
        for m in self.mirrors:
            try:
                rec = m.post(payload)
            except Exception as exc:  # pragma: no cover - defensive
                rec = CommitRecord(
                    kind=payload.kind,
                    root_hex="0x" + payload.root.hex(),
                    window_start=payload.window_start,
                    window_end=payload.window_end,
                    nonce=payload.nonce,
                    error=f"mirror[{m.chain_id}] raised: {exc}",
                )
                _log.error(
                    "oracle.anchor.mirror_raised",
                    kind=payload.kind,
                    chain_id=m.chain_id,
                    err=str(exc),
                )
            self.mirror_records.append(rec)
        return canonical_rec

    async def post_async(self, payload: CommitPayload) -> CommitRecord:
        """Async fan-out: canonical + all mirrors run concurrently. The
        scheduler waits on the canonical record (so nonce sync stays
        attached to Kite); mirror outcomes are recorded asynchronously.
        Mirror exceptions are caught and logged."""
        tasks: list[asyncio.Task[CommitRecord]] = [
            asyncio.create_task(self.canonical.post_async(payload))
        ]
        for m in self.mirrors:
            tasks.append(asyncio.create_task(m.post_async(payload)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        canonical_outcome = results[0]
        if isinstance(canonical_outcome, BaseException):
            raise canonical_outcome
        canonical_rec: CommitRecord = canonical_outcome  # type: ignore[assignment]

        for idx, outcome in enumerate(results[1:], start=0):
            mirror = self.mirrors[idx]
            if isinstance(outcome, BaseException):
                rec = CommitRecord(
                    kind=payload.kind,
                    root_hex="0x" + payload.root.hex(),
                    window_start=payload.window_start,
                    window_end=payload.window_end,
                    nonce=payload.nonce,
                    error=f"mirror[{mirror.chain_id}] raised: {outcome}",
                )
                _log.error(
                    "oracle.anchor.mirror_raised",
                    kind=payload.kind,
                    chain_id=mirror.chain_id,
                    err=str(outcome),
                )
            else:
                rec = outcome
            self.mirror_records.append(rec)

        return canonical_rec


__all__ = [
    "AnchorPoster",
    "CommitPayload",
    "CommitRecord",
    "MultiChainAnchorPoster",
    "PriceAnchorScheduler",
    "SignedCommit",
    "YieldAnchorScheduler",
    "sign_commit",
]
