"""Minimal web3 client for the WS4.B CLI commands.

`StakeClient` wraps the two-tx flow `helios stake top-up` needs (USDC
approve → `StrategyRegistry.topUpStake`) plus the symmetric
withdrawal calls. `VerifierReader` is a read-only `eth_call` against
`TradeAttestationVerifier.verify` for `helios test-proof`.

Both are intentionally narrow — the runtime services (`sentinel`,
`reference-strategies/*/runtime.py`) own the higher-level submission
loop. The CLI just needs the bare-minimum signed-tx primitives."""

from __future__ import annotations

from typing import Any

from eth_account import Account
from helios_contracts_abi.abis import (
    IStrategyRegistry_ABI,
    ITradeAttestationVerifier_ABI,
)
from web3 import Web3

# `IERC20.approve(spender, amount)` — keep it inline so the CLI doesn't
# carry the full ERC-20 ABI just for one selector.
_ERC20_APPROVE_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "approve",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    }
]

_RECEIPT_TIMEOUT_SEC = 30


class StakeClient:
    """Signs and submits the stake-management txs.

    Lazy: opens the RPC connection on first call so unit tests that
    construct a client without a running node don't trip a connection
    error."""

    def __init__(
        self,
        *,
        rpc_url: str,
        operator_pk: str,
        chain_id: int,
        registry: str,
        usdc: str,
    ) -> None:
        self._rpc_url = rpc_url
        self._operator_pk = operator_pk
        self._chain_id = chain_id
        self._registry_address = Web3.to_checksum_address(registry)
        self._usdc_address = Web3.to_checksum_address(usdc)
        self._w3: Web3 | None = None
        self._account: Any = None
        self._registry: Any = None
        self._usdc: Any = None

    def _ensure(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        try:
            self._account = Account.from_key(self._operator_pk)
        except Exception as exc:
            raise RuntimeError(f"invalid operator key: {type(exc).__name__}") from None
        self._registry = self._w3.eth.contract(
            address=self._registry_address, abi=IStrategyRegistry_ABI
        )
        self._usdc = self._w3.eth.contract(address=self._usdc_address, abi=_ERC20_APPROVE_ABI)

    def approve(self, amount: int) -> str:
        self._ensure()
        assert self._usdc is not None
        return self._send(self._usdc.functions.approve(self._registry_address, int(amount)))

    def top_up(self, strategy_id: str, amount: int) -> str:
        self._ensure()
        assert self._registry is not None
        return self._send(
            self._registry.functions.topUpStake(Web3.to_checksum_address(strategy_id), int(amount))
        )

    def initiate_withdrawal(self, strategy_id: str, amount: int) -> str:
        self._ensure()
        assert self._registry is not None
        return self._send(
            self._registry.functions.initiateStakeWithdrawal(
                Web3.to_checksum_address(strategy_id), int(amount)
            )
        )

    def claim_withdrawal(self, strategy_id: str) -> str:
        self._ensure()
        assert self._registry is not None
        return self._send(
            self._registry.functions.claimStakeWithdrawal(Web3.to_checksum_address(strategy_id))
        )

    def _send(self, fn: Any) -> str:
        assert self._w3 is not None
        assert self._account is not None
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
                "chainId": self._chain_id,
                # Same posture as services/sentinel/onchain.py: legacy gasPrice
                # avoids EIP-1559 fee estimation on RPCs that don't implement
                # `eth_feeHistory`.
                "gasPrice": self._w3.eth.gas_price,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=_RECEIPT_TIMEOUT_SEC)
        if receipt["status"] != 1:
            raise RuntimeError(f"tx reverted: {tx_hash.hex()}")
        return tx_hash.hex()


class VerifierReader:
    """Read-only `eth_call` against `TradeAttestationVerifier.verify`."""

    def __init__(self, *, rpc_url: str, verifier_address: str) -> None:
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(verifier_address),
            abi=ITradeAttestationVerifier_ABI,
        )

    def verify(self, declared_class: bytes, proof: bytes, public_inputs: list[int]) -> bool:
        if len(declared_class) != 32:
            raise ValueError(f"declared_class must be 32 bytes, got {len(declared_class)}")
        result: bool = self._contract.functions.verify(
            declared_class, proof, [int(p) for p in public_inputs]
        ).call()
        return bool(result)


__all__ = ["StakeClient", "VerifierReader"]
