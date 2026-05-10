"""Idempotent `StrategyRegistry.commitInitialParamsHash` helper.

`StrategyVault.executeWithProof` reads `_activeParamsHash() ==
publicInputs[PI_PARAMS_HASH]` from `StrategyRegistry.paramsHashOf(vault)`
(`contracts/src/StrategyVault.sol:470`). An uninitialized hash is
`bytes32(0)` and *every* proof reverts `ParamsHashMismatch` until the
strategy operator commits the canonical Poseidon hash of its operator
bounds. The deploy script intentionally leaves this unset
(`contracts/script/DeployPhase6MultiAssetVaults.s.sol:24-26` —
"NOT commit `paramsHash` — that's done off-chain by the strategy SDK")
so the operator can change bounds before bring-up without redeploying.

Each strategy class hashes a different field tuple, but the wire format
(bytes32 stored on the registry) is the same. The runtime computes the
class-specific Poseidon (see each `*_v1/witness.py`'s `params_hash`
field) and passes it here. This module only deals with the on-chain
side: read → commit-if-zero → hard-fail-on-mismatch.

Idempotent by design: safe to call on every container start. The
mismatch branch is intentional — there's no rotate path on the
registry, so a wrong hash means a redeploy is the only fix.

Used by all three reference-strategy services (`reference-strategies/
{momentum_v1,mean_reversion_v1,yield_rotation_v1}/src/.../service.py`)
in their FastAPI `lifespan` hook.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from eth_account import Account
from web3 import Web3
from web3.contract import Contract

_log = logging.getLogger(__name__)

# Minimal ABI — `paramsHashOf` (view) + `commitInitialParamsHash`
# (state-changing). Kept inline so this module has no workspace runtime
# deps (the published wheel installs from PyPI without
# `helios-contracts-abi`).
_REGISTRY_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "paramsHashOf",
        "stateMutability": "view",
        "inputs": [{"name": "vault", "type": "address"}],
        "outputs": [{"name": "", "type": "bytes32"}],
    },
    {
        "type": "function",
        "name": "commitInitialParamsHash",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "vault", "type": "address"},
            {"name": "paramsHash", "type": "bytes32"},
        ],
        "outputs": [],
    },
]


class ParamsHashMismatchError(RuntimeError):
    """Raised when the registry already has a different hash committed
    for this vault. There is no rotate path; the strategy must either
    revert to the committed bounds or the operator must redeploy the
    vault. The runtime treats this as fatal so a misconfigured strategy
    never silently signs proofs the verifier will reject."""

    def __init__(self, *, vault: str, on_chain: bytes, computed: bytes) -> None:
        self.vault = vault
        self.on_chain = on_chain
        self.computed = computed
        super().__init__(
            f"params hash mismatch for vault {vault}: "
            f"on-chain=0x{on_chain.hex()} computed=0x{computed.hex()}"
        )


@dataclass(frozen=True, slots=True)
class CommitOutcome:
    """What `ensure_params_committed` did. `committed_now` is True iff
    this call broadcast a `commitInitialParamsHash` tx; False means the
    on-chain hash already matched and no tx was sent."""

    vault: str
    params_hash: bytes
    committed_now: bool
    tx_hash: str | None = None


def _normalize_pk(pk: str) -> str:
    return pk if pk.startswith("0x") else f"0x{pk}"


def ensure_params_committed(
    *,
    w3: Web3,
    registry_address: str,
    vault_address: str,
    params_hash: bytes,
    operator_pk: str,
    gas_limit: int = 200_000,
) -> CommitOutcome:
    """Read `paramsHashOf(vault)`; commit `params_hash` if zero; raise
    `ParamsHashMismatchError` if non-zero and different. Returns a
    `CommitOutcome` with the tx hash when a commit landed.

    The signer is the strategy operator (matches `manifest.operator`
    on-chain — registry's `commitInitialParamsHash` is gated by
    `onlyStrategyOperator(vault)` at `StrategyRegistry.sol`). Uses a
    fixed gas limit of 200_000 because `commitInitialParamsHash` is a
    single SSTORE + event emit (~50k gas in practice; the headroom
    covers cold-storage warmup).

    Connectionless reads (RPC failures) propagate as web3.py exceptions;
    callers should catch + log per their tolerance. The function does
    not retry — bring-up is a one-shot per container start.
    """
    if len(params_hash) != 32:
        raise ValueError(f"params_hash must be 32 bytes, got {len(params_hash)}")

    registry: Contract = w3.eth.contract(
        address=Web3.to_checksum_address(registry_address),
        abi=_REGISTRY_ABI,
    )
    vault_cs = Web3.to_checksum_address(vault_address)
    on_chain: bytes = registry.functions.paramsHashOf(vault_cs).call()

    if int.from_bytes(on_chain, "big") == 0:
        # `LocalAccount` is a stable runtime contract; `eth-account`'s
        # type stubs collide with `web3.py`'s `TxParams` annotation in a
        # way that's purely cosmetic (the actual runtime accepts both).
        signer: Any = Account.from_key(_normalize_pk(operator_pk))
        nonce = w3.eth.get_transaction_count(signer.address)
        tx: Any = registry.functions.commitInitialParamsHash(
            vault_cs, params_hash
        ).build_transaction(
            {
                "from": signer.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": w3.eth.gas_price,
                "chainId": w3.eth.chain_id,
            }
        )
        signed = signer.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            raise RuntimeError(f"commitInitialParamsHash reverted: tx={tx_hash.hex()}")
        _log.info(
            "strategy.params_hash.committed vault=%s hash=0x%s tx=%s",
            vault_cs,
            params_hash.hex(),
            tx_hash.hex(),
        )
        return CommitOutcome(
            vault=vault_cs,
            params_hash=params_hash,
            committed_now=True,
            tx_hash=tx_hash.hex() if isinstance(tx_hash, bytes) else str(tx_hash),
        )

    if on_chain != params_hash:
        raise ParamsHashMismatchError(vault=vault_cs, on_chain=on_chain, computed=params_hash)

    _log.info(
        "strategy.params_hash.already_committed vault=%s hash=0x%s",
        vault_cs,
        params_hash.hex(),
    )
    return CommitOutcome(vault=vault_cs, params_hash=params_hash, committed_now=False)


__all__ = [
    "CommitOutcome",
    "ParamsHashMismatchError",
    "ensure_params_committed",
]
