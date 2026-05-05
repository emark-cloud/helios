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
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import structlog
from _template.web3_consts import RECEIPT_TIMEOUT_SEC
from eth_account import Account
from eth_account.messages import encode_typed_data
from helios_contracts_abi.abis import IOracleAnchor_ABI
from web3 import Web3
from web3.types import TxReceipt

from oracle.state import SnapshotStore
from oracle.yield_state import YieldStore

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

    pending: list[CommitRecord] = field(default_factory=list)
    _w3: Any = field(default=None, init=False, repr=False)
    _account: Any = field(default=None, init=False, repr=False)
    _contract: Any = field(default=None, init=False, repr=False)

    @property
    def live(self) -> bool:
        return bool(self.rpc_url and self.signer_pk and self.anchor_address)

    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
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
            raise RuntimeError(f"tx reverted: {tx_hash.hex()}")
        return tx_hash.hex(), int(receipt["blockNumber"])


@dataclass
class PriceAnchorScheduler:
    """Drives `AnchorPoster.post(price)` every N snapshot bars.

    Phase 2 cadence: commit per `interval_bars` bars (default 50) per
    asset. The scheduler keeps a per-asset `last_committed_ts` so each
    new commit window is anchored to the previous one's `windowEnd`.
    """

    store: SnapshotStore
    poster: AnchorPoster
    interval_bars: int = 50
    chain_depth: int = 16  # how many bars feed into the Poseidon root

    _last_window_end: dict[str, int] = field(default_factory=dict)
    _bar_counter: dict[str, int] = field(default_factory=dict)
    _nonce: int = 0

    def on_bar(self, asset: str) -> CommitRecord | None:
        """Sync entry point — convenient for tests + scenario replay."""
        payload = self._prepare(asset)
        return self.poster.post(payload) if payload is not None else None

    async def on_bar_async(self, asset: str) -> CommitRecord | None:
        """Async entry point. Used in production from `Poller._on_snapshot`
        so the up-to-30s receipt wait runs on a worker thread, not the
        event loop. Same payload-building semantics as `on_bar`."""
        payload = self._prepare(asset)
        return await self.poster.post_async(payload) if payload is not None else None

    def _prepare(self, asset: str) -> CommitPayload | None:
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
        prev_end = self._last_window_end.get(asset)
        # Each commit's window must be strictly after the previous; nudge
        # `windowStart` past `prev_end` if the snapshots overlap (the
        # contract enforces `ws >= prev.we`).
        window_start = max(oldest_ts, prev_end if prev_end is not None else 0)
        window_end = newest_ts
        if window_end <= window_start:
            return None  # not enough fresh ticks yet

        payload = CommitPayload(
            kind="price",
            root=root_int.to_bytes(32, "big"),
            window_start=window_start,
            window_end=window_end,
            nonce=self._nonce,
        )
        self._nonce += 1
        self._last_window_end[asset] = window_end
        return payload


@dataclass
class YieldAnchorScheduler:
    """Same as `PriceAnchorScheduler` but for the yield store."""

    store: YieldStore
    poster: AnchorPoster
    interval_bars: int = 50
    chain_depth: int = 16

    _last_window_end: dict[str, int] = field(default_factory=dict)
    _bar_counter: dict[str, int] = field(default_factory=dict)
    _nonce: int = 0

    def on_bar(self, market_id: str) -> CommitRecord | None:
        payload = self._prepare(market_id)
        return self.poster.post(payload) if payload is not None else None

    async def on_bar_async(self, market_id: str) -> CommitRecord | None:
        payload = self._prepare(market_id)
        return await self.poster.post_async(payload) if payload is not None else None

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
        prev_end = self._last_window_end.get(market_id)
        window_start = max(oldest_ts, prev_end if prev_end is not None else 0)
        window_end = newest_ts
        if window_end <= window_start:
            return None

        payload = CommitPayload(
            kind="yield",
            root=root_int.to_bytes(32, "big"),
            window_start=window_start,
            window_end=window_end,
            nonce=self._nonce,
        )
        self._nonce += 1
        self._last_window_end[market_id] = window_end
        return payload


__all__ = [
    "AnchorPoster",
    "CommitPayload",
    "CommitRecord",
    "PriceAnchorScheduler",
    "SignedCommit",
    "YieldAnchorScheduler",
    "sign_commit",
]
