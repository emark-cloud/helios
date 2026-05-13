"""On-chain `ReputationAnchor.postReputationUpdate` submission.

Address-gated: when `REPUTATION_ANCHOR_ADDRESS` is unset, the poster
records what it *would have* submitted (`pending`) and returns. Same
posture as `services/sentinel/onchain.py` and the momentum executor —
keeps the engine path uniform across pre/post-deploy environments.

The signer key driving this submission is the same one the engine uses
to sign updates. `ReputationAnchor.postReputationUpdate` recovers the
EIP-712 signature against `reputationSigner`, so caller and signer must
agree. In Phase 1 e2e (Track A) we set both to the deployer key. In
Track B / production we set both to a dedicated `REPUTATION_SIGNER_PK`.

Two on-chain shapes coexist (see `signer.py` typehash_version):

- **v1** (Phase 1, on-chain at 0x51c07adf… on Kite testnet): 7-field
  `ReputationData` struct (no `componentsHash`). Function selector
  `0xcc177986`. This is the registry-bound anchor.
- **v2** (Phase 2 WS3.A onwards): 8-field struct with `componentsHash`.
  Function selector `0x2dab51f6`. Deployed as a sidecar at
  0x735680a3… on Kite testnet; not registry-bound until a Phase-5/6
  mainnet cutover (`docs/reputation-v1-v2-cutover.md`).

The shared `helios_contracts_abi.abis.IReputationAnchor_ABI` reflects
the **v2** shape because the Foundry artifacts mirror the current
source. To stay compatible with v1-shaped anchors (where the registries
are pinned via `address immutable reputationAnchor`, so we cannot
swap the deployed anchor out), we keep an in-file v1 ABI fragment and
branch on `typehash_version` when building the call. Engines pointed
at the v1 anchor sign v1 typehashes AND submit v1-shaped calldata;
engines pointed at v2 use the shared ABI as-is.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

import structlog
from _template.web3_consts import RECEIPT_TIMEOUT_SEC
from eth_account import Account
from helios_contracts_abi.abis import IReputationAnchor_ABI
from web3 import Web3
from web3.types import TxReceipt

from reputation.signer import SignedUpdate

# v1 ABI fragment — the 7-field ReputationData struct (no componentsHash)
# that the on-chain v1 anchor at 0x51c07adf… on Kite testnet expects.
# Function selector resolves to 0xcc177986. Keep the rest of the v1 ABI
# minimal: we only call `postReputationUpdate` from this module.
_IREPUTATION_ANCHOR_V1_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "postReputationUpdate",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "actor", "type": "address"},
            {"name": "actorType", "type": "uint8"},
            {
                "name": "data",
                "type": "tuple",
                "components": [
                    {"name": "currentScore", "type": "int256"},
                    {"name": "lastUpdateBlock", "type": "uint256"},
                    {"name": "totalAttestedTrades", "type": "uint256"},
                    {"name": "totalRealizedPnL", "type": "uint256"},
                    {"name": "maxDrawdownBps", "type": "uint256"},
                    {"name": "proofValidityRateBps", "type": "uint256"},
                    {"name": "actorType", "type": "uint8"},
                ],
            },
            {"name": "signerSignature", "type": "bytes"},
        ],
        "outputs": [],
    }
]

# Cap for the in-memory `pending` ring. The reputation engine ticks every
# few minutes and the anchor records one entry per submit; 4096 keeps
# ~weeks of history visible to /v1/audit while bounding RSS for the
# always-on engine. Older entries fall off silently — they're already
# durable on-chain.
_PENDING_RING_CAP = 4096

# Minimal view-only ABI for the registry pre-flight (`RegistryActiveCheck`).
# Both registries share an `*Of(address)` getter returning a struct with
# `registeredAt` (uint64) + `active` (bool); the field shape differs but
# only the two fields we read need to line up by position, which they do
# (see `IStrategyRegistry.StrategyEntry` vs `IAllocatorRegistry.AllocatorEntry`).
_REGISTRY_PROBE_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "strategyOf",
        "stateMutability": "view",
        "inputs": [{"name": "strategyId", "type": "address"}],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "vault", "type": "address"},
                    {"name": "operator", "type": "address"},
                    {"name": "declaredClass", "type": "bytes32"},
                    {"name": "stakeAmount", "type": "uint256"},
                    {"name": "currentReputation", "type": "int256"},
                    {"name": "registeredAt", "type": "uint64"},
                    {"name": "active", "type": "bool"},
                ],
            }
        ],
    },
    {
        "type": "function",
        "name": "allocatorOf",
        "stateMutability": "view",
        "inputs": [{"name": "allocatorId", "type": "address"}],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "name", "type": "string"},
                    {"name": "operatorVault", "type": "address"},
                    {"name": "operator", "type": "address"},
                    {"name": "rankingFunctionHash", "type": "bytes32"},
                    {"name": "supportedClasses", "type": "bytes32[]"},
                    {"name": "feeRateBps", "type": "uint16"},
                    {"name": "stakeAmount", "type": "uint256"},
                    {"name": "currentReputation", "type": "int256"},
                    {"name": "totalUsers", "type": "uint256"},
                    {"name": "totalCapitalManaged", "type": "uint256"},
                    {"name": "registeredAt", "type": "uint64"},
                    {"name": "active", "type": "bool"},
                    {"name": "isReferenceBrand", "type": "bool"},
                ],
            }
        ],
    },
]

_log = structlog.get_logger(__name__)


class RegistryActiveCheck:
    """On-chain pre-flight for `AnchorPoster.post()`.

    Reads `*Of(actor)` on the bound registries and returns False when an
    actor isn't registered (`registeredAt == 0`) or has been deactivated
    (`active == false`). Without this filter, the engine submits
    `postReputationUpdate` for every Goldsky-reported actor whose
    `Strategy.active == true` — which includes pre-WS11 legacy cohorts
    that the new SR-v3 doesn't know about, so every such submission
    reverts `StrategyNotFound()` (`0x5be2b482`) and wastes ~117k gas.

    Configured via the canonical SR-v3 / AR-v2 addresses
    (`REPUTATION_STRATEGY_REGISTRY_ADDRESS`,
    `REPUTATION_ALLOCATOR_REGISTRY_ADDRESS`). Either may be unset, in
    which case the corresponding actor type bypasses the check —
    matches the test-mode posture of `AnchorPoster.live`.
    """

    def __init__(
        self,
        rpc_url: str,
        strategy_registry: str = "",
        allocator_registry: str = "",
    ) -> None:
        self._rpc_url = rpc_url
        self._strategy_registry = strategy_registry
        self._allocator_registry = allocator_registry
        # Lazy handles — same posture as AnchorPoster so test harnesses
        # don't have to spin up an RPC stub just to construct the engine.
        self._w3: Web3 | None = None
        self._strategy_contract: Any = None
        self._allocator_contract: Any = None

    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        if self._strategy_registry:
            self._strategy_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(self._strategy_registry),
                abi=_REGISTRY_PROBE_ABI,
            )
        if self._allocator_registry:
            self._allocator_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(self._allocator_registry),
                abi=_REGISTRY_PROBE_ABI,
            )

    def is_active(self, actor: str, actor_type: int) -> bool:
        """True if the actor is registered AND active in the bound
        registry. When the relevant registry address is unset, returns
        True (i.e. defers to whatever the anchor's own checks decide).
        On any RPC error, returns True — better to let the anchor surface
        the real error than silently swallow a transient blip."""
        self._ensure_live()
        if actor_type == 0:  # ActorType.STRATEGY
            contract = self._strategy_contract
            getter = "strategyOf"
        elif actor_type == 1:  # ActorType.ALLOCATOR
            contract = self._allocator_contract
            getter = "allocatorOf"
        else:
            return True
        if contract is None:
            return True
        try:
            entry = contract.functions[getter](Web3.to_checksum_address(actor)).call()
        except Exception as exc:
            _log.warning("reputation.registry_probe.error", actor=actor, err=str(exc))
            return True
        # `strategyOf` returns 7-tuple, `allocatorOf` returns 13-tuple.
        # `registeredAt` + `active` are the last two slots in both layouts
        # except allocator has a trailing `isReferenceBrand` bool after
        # `active`. Pull by struct index to avoid ordering drift.
        if actor_type == 0:
            registered_at = int(entry[5])
            active = bool(entry[6])
        else:
            registered_at = int(entry[10])
            active = bool(entry[11])
        return registered_at > 0 and active


@dataclass(slots=True)
class PostedUpdate:
    actor: str
    score_e4: int
    tx_hash: str = ""
    submitted: bool = False
    error: str = ""


class AnchorPoster:
    def __init__(
        self,
        rpc_url: str,
        signer_pk: str,
        anchor_address: str,
        chain_id: int,
        typehash_version: str = "1",
        registry_check: RegistryActiveCheck | None = None,
    ) -> None:
        if typehash_version not in {"1", "2"}:
            raise ValueError(f"unsupported typehash version: {typehash_version!r}")
        self._rpc_url = rpc_url
        self._signer_pk = signer_pk
        self._anchor = anchor_address
        self._chain_id = chain_id
        self._typehash_version = typehash_version
        self._live = bool(rpc_url and signer_pk and anchor_address)
        self._registry_check = registry_check
        self.pending: deque[PostedUpdate] = deque(maxlen=_PENDING_RING_CAP)
        # Serialize `_submit`. Phase-3 review MEDIUM: `_submit` reads the
        # on-chain pending nonce inline, signs, and sends. Two concurrent
        # callers (strategy tick + allocator tick scheduled at the same
        # cadence; or a manual /v1/repost while the engine is mid-tick)
        # would read the same nonce, sign two txs against it, and one
        # would silently bounce. The lock is held across the
        # nonce-read → sign → send → wait_for_receipt path so the next
        # caller starts with the fresh post-mining nonce.
        self._submit_lock = threading.Lock()

        # Lazy live handles.
        self._w3: Web3 | None = None
        self._account: Any = None
        self._contract: Any = None

    @property
    def live(self) -> bool:
        return self._live

    def post(self, signed: SignedUpdate) -> PostedUpdate:
        """Sync submit. Async callers should use `post_async` so the
        up-to-30s `wait_for_transaction_receipt` runs on a worker thread."""
        result = PostedUpdate(actor=signed.update.actor, score_e4=signed.update.current_score)
        if not self._live:
            self.pending.append(result)
            _log.info(
                "reputation.anchor.dry_run",
                actor=signed.update.actor,
                score_e4=signed.update.current_score,
            )
            return result
        # Pre-flight: drop submissions for actors the bound registries
        # don't know about. The Goldsky candidate set leaks legacy
        # cohorts (V1 registry never deactivated them when WS11 swapped
        # the anchor to SR-v3 / AR-v2), so without this filter every
        # legacy actor wastes ~117k gas and reverts `StrategyNotFound`
        # or `AllocatorNotFound`. See memory `project_reputation_registry_filter`.
        if self._registry_check is not None:
            actor_type = int(signed.update.actor_type)
            if not self._registry_check.is_active(signed.update.actor, actor_type):
                result.error = "skipped: actor not in active registry set"
                self.pending.append(result)
                _log.info(
                    "reputation.anchor.skip_not_in_registry",
                    actor=signed.update.actor,
                    actor_type=actor_type,
                )
                return result
        try:
            with self._submit_lock:
                tx_hash, block_number = self._submit(signed)
            result.tx_hash = tx_hash
            result.submitted = True
            _log.info(
                "reputation.anchor.posted",
                actor=signed.update.actor,
                score_e4=signed.update.current_score,
                tx_hash=tx_hash,
                block=block_number,
            )
        except Exception as exc:
            result.error = str(exc)
            _log.error(
                "reputation.anchor.submit_failed",
                actor=signed.update.actor,
                err=str(exc),
            )
        self.pending.append(result)
        return result

    async def post_async(self, signed: SignedUpdate) -> PostedUpdate:
        """Run the blocking submit on a worker thread. Used from the async
        engine `tick_once` so the event loop keeps draining other strategies'
        scoring + WS subscribers while a single tx waits for its receipt."""
        return await asyncio.to_thread(self.post, signed)

    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        pk = self._signer_pk if self._signer_pk.startswith("0x") else "0x" + self._signer_pk
        try:
            self._account = Account.from_key(pk)
        except Exception as exc:  # pragma: no cover — defensive
            # Don't let the raised value (which may include the malformed key
            # material) propagate up into structlog or a stack trace.
            raise RuntimeError(f"invalid REPUTATION_SIGNER_PK: {type(exc).__name__}") from None
        # Pick the ABI that matches the on-chain struct shape. v1 anchor
        # (registry-bound on Kite testnet) has a 7-field ReputationData;
        # v2 anchor (post-WS3.A) adds componentsHash. The function selector
        # differs between the two, so sending v2-shaped calldata to a v1
        # anchor fails with `('execution reverted', 'no data')` (unknown
        # selector → fallback revert).
        abi = _IREPUTATION_ANCHOR_V1_ABI if self._typehash_version == "1" else IReputationAnchor_ABI
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._anchor),
            abi=abi,
        )

    def _submit(self, signed: SignedUpdate) -> tuple[str, int]:
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        assert self._contract is not None

        u = signed.update
        # ReputationData tuple shape follows the anchor's on-chain struct:
        # v1 = 7 fields (currentScore, lastUpdateBlock, totalAttestedTrades,
        #   totalRealizedPnL, maxDrawdownBps, proofValidityRateBps, actorType)
        # v2 = same + componentsHash (8th field, bytes32, right-padded).
        # actorType is duplicated as a top-level arg because that's the
        # function signature shape — the struct copy is what gets signed
        # in the EIP-712 typed payload.
        data_tuple: tuple[Any, ...] = (
            int(u.current_score),
            int(u.last_update_block),
            int(u.total_attested_trades),
            int(u.total_realized_pnl),
            int(u.max_drawdown_bps),
            int(u.proof_validity_rate_bps),
            int(u.actor_type),
        )
        if self._typehash_version == "2":
            components_hash = u.components_hash if u.components_hash else b""
            if len(components_hash) > 32:
                raise ValueError("components_hash exceeds 32 bytes")
            data_tuple = (*data_tuple, components_hash.rjust(32, b"\x00"))
        fn = self._contract.functions.postReputationUpdate(
            Web3.to_checksum_address(u.actor),
            int(u.actor_type),
            data_tuple,
            signed.signature,
        )
        # Override web3's default gas estimate with a 50% buffer. The
        # Kite testnet RPC under-estimates `postReputationUpdate` by
        # ~15-25% — the inner `strategyRegistry.updateReputation` callout
        # plus its event emission lands at ~125k gas, while estimateGas
        # reports ~100k (first-write cold-storage SSTOREs aren't fully
        # accounted for, particularly when prev.lastUpdateBlock was 0).
        # Half the actors per tick hit OutOfGas under the default; adding
        # headroom eliminates the failure mode without risking real
        # over-spend (gas is refunded for unused units).
        from_addr = self._account.address
        try:
            estimated = self._contract.functions.postReputationUpdate(
                Web3.to_checksum_address(u.actor),
                int(u.actor_type),
                data_tuple,
                signed.signature,
            ).estimate_gas({"from": from_addr})
        except Exception:
            estimated = 200_000  # fallback when estimateGas itself trips
        gas_limit = max(int(estimated * 3 // 2), 200_000)
        tx = fn.build_transaction(
            {
                "from": from_addr,
                "nonce": self._w3.eth.get_transaction_count(from_addr, "pending"),
                "chainId": self._chain_id,
                "gasPrice": self._w3.eth.gas_price,
                "gas": gas_limit,
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


__all__ = ["AnchorPoster", "PostedUpdate"]
