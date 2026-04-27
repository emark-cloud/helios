"""Sentinel's chain client.

Three responsibilities:

1. Read live state from the AllocatorVault + StrategyVault that Goldsky
   doesn't yet surface fast enough — `AllocatorVault.allocationOf(user,
   strategy)` (capital deployed + HWM + defundedAt) and
   `StrategyVault.navOf(allocatorVault)` (current NAV share).
2. Submit the four operator-driven calls: `allocateToStrategy`,
   `defundStrategy`, `rebalance`, `settleStrategyFee`.
3. (Optional) register Sentinel on `AllocatorRegistry` with
   `isReferenceBrand=true`, name `"Helios Sentinel"`. Phase 1 expects a
   one-shot CLI / startup hook to run this once after WS3 e2e deploys
   contracts; the client just exposes the call.

Phase 1 ships an *address-gated* runner: when `ALLOCATOR_VAULT_ADDRESS`
is unset (i.e. before WS3 e2e), the on-chain client is a no-op that
records what it *would have* done. Same posture as the reputation
engine's `REPUTATION_ANCHOR_ADDRESS` gate.

WS3 wired live-mode submission via `web3.py`. The decision loop is
sync at the call site (`_apply_diffs`); chain RPC happens inline.
On local anvil this is sub-second; on Kite testnet (1s blocks) the
worst case is a single-block confirm wait. The 60s drawdown tick
gives ample headroom.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from eth_account import Account
from helios_contracts_abi.abis import IAllocatorVault_ABI
from web3 import Web3
from web3.types import TxReceipt

from sentinel.state import AllocationState

_log = structlog.get_logger(__name__)

# Confirmation timeout per call. Local anvil mines instantly; Kite testnet
# mines every ~1s. 30s is generous without being silly.
_RECEIPT_TIMEOUT_SEC = 30


@dataclass(slots=True)
class OnChainCall:
    """A planned (and possibly submitted) chain call.

    Mutable so the live path can attach tx_hash / receipt status without
    forcing the dry-run path to allocate a separate result type.
    """

    method: str
    user: str
    strategy: str | None
    amount: int = 0
    reason: str = ""
    weights_bps: tuple[int, ...] = ()
    strategies: tuple[str, ...] = ()
    tx_hash: str = ""
    submitted: bool = False
    error: str = ""


class OnChainRunner:
    """Tx-submission boundary.

    Live mode: takes a `web3.Web3` + signing key, submits real txs.
    Stub mode: when `allocator_vault_address` is empty, records calls
    in `pending` for tests / dry-runs. The decision loop never branches
    on which mode is active — it just calls into the runner.
    """

    def __init__(
        self,
        rpc_url: str,
        operator_pk: str,
        allocator_vault_address: str,
        allocator_registry_address: str,
        chain_id: int,
    ) -> None:
        self._rpc_url = rpc_url
        self._operator_pk = operator_pk
        self._allocator_vault = allocator_vault_address
        self._allocator_registry = allocator_registry_address
        self._chain_id = chain_id
        self._live = bool(rpc_url and operator_pk and allocator_vault_address)
        self.pending: list[OnChainCall] = []

        # Live-mode handles initialised lazily on first submit so dry-run
        # tests don't need to spin up an RPC client.
        self._w3: Web3 | None = None
        self._account: Any = None
        self._vault_contract: Any = None

    @property
    def live(self) -> bool:
        return self._live

    @property
    def allocator_vault(self) -> str:
        return self._allocator_vault

    def allocate(self, user: str, strategy: str, amount: int) -> OnChainCall:
        return self._submit(
            OnChainCall(method="allocateToStrategy", user=user, strategy=strategy, amount=amount)
        )

    def defund(self, user: str, strategy: str, reason: str) -> OnChainCall:
        return self._submit(
            OnChainCall(method="defundStrategy", user=user, strategy=strategy, reason=reason)
        )

    def rebalance(
        self,
        user: str,
        strategies: list[str],
        weights_bps: list[int],
    ) -> OnChainCall:
        return self._submit(
            OnChainCall(
                method="rebalance",
                user=user,
                strategy=None,
                strategies=tuple(strategies),
                weights_bps=tuple(weights_bps),
            )
        )

    def settle_fee(self, user: str, strategy: str) -> OnChainCall:
        return self._submit(OnChainCall(method="settleStrategyFee", user=user, strategy=strategy))

    async def read_allocation(self, user: str, strategy: str) -> AllocationState | None:
        """Mirror current on-chain allocation state.

        Phase 1 stub returns None when the runner is not live; the loop
        falls back to its in-memory mirror. Live mode reads
        `AllocatorVault.allocationOf(user, strategy)`.
        """
        if not self._live:
            return None
        self._ensure_live()
        assert self._vault_contract is not None
        record = self._vault_contract.functions.allocationOf(
            Web3.to_checksum_address(user), Web3.to_checksum_address(strategy)
        ).call()
        # Tuple matches IAllocatorVault.AllocationRecord. We only need
        # capital_deployed + high_water_mark for the Phase 1 loop; rest
        # land when the loop wants finer state. record[0]=strategy,
        # [1]=capitalDeployed, [2]=highWaterMark, [3]=defundedAt, [4]=lastUpdate.
        capital_deployed = int(record[1])
        hwm = int(record[2])
        defunded_at = int(record[3])
        return AllocationState(
            strategy_id=strategy,
            chain_id=self._chain_id,
            declared_class="",
            capital_deployed_usd=capital_deployed,
            high_water_mark_usd=hwm,
            nav_usd=capital_deployed,  # NAV reads come from StrategyVault, wired in WS4
            last_rebalance_ts=0,
            defunded=defunded_at != 0,
        )

    def _submit(self, call: OnChainCall) -> OnChainCall:
        if not self._live:
            self.pending.append(call)
            _log.info(
                "sentinel.onchain.dry_run",
                method=call.method,
                user=call.user,
                strategy=call.strategy,
                amount=call.amount,
                reason=call.reason,
            )
            return call
        try:
            self._send_live(call)
        except Exception as exc:
            call.error = str(exc)
            _log.error(
                "sentinel.onchain.submit_failed",
                method=call.method,
                user=call.user,
                strategy=call.strategy,
                err=str(exc),
            )
        # Pending list mirrors *all* attempted calls so `/v1/users/.../events`
        # consumers see the same surface in live + dry modes.
        self.pending.append(call)
        return call

    # ── Live submission ───────────────────────────────────────
    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        self._account = Account.from_key(self._operator_pk)
        self._vault_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._allocator_vault),
            abi=IAllocatorVault_ABI,
        )

    def _send_live(self, call: OnChainCall) -> None:
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        assert self._vault_contract is not None

        fn = self._build_function(call)
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
                "chainId": self._chain_id,
                # Anvil + Kite both honour legacy gasPrice; explicit value avoids
                # web3's EIP-1559 fee estimation hitting `eth_feeHistory` which
                # some forks (and our anvil container) don't implement.
                "gasPrice": self._w3.eth.gas_price,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        call.tx_hash = tx_hash.hex()
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=_RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"tx reverted: {call.tx_hash}")
        call.submitted = True
        _log.info(
            "sentinel.onchain.submitted",
            method=call.method,
            tx_hash=call.tx_hash,
            block=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
        )

    def _build_function(self, call: OnChainCall) -> Any:
        assert self._vault_contract is not None
        if call.method == "allocateToStrategy":
            return self._vault_contract.functions.allocateToStrategy(
                Web3.to_checksum_address(call.user),
                Web3.to_checksum_address(_require_strategy(call)),
                int(call.amount),
            )
        if call.method == "defundStrategy":
            return self._vault_contract.functions.defundStrategy(
                Web3.to_checksum_address(call.user),
                Web3.to_checksum_address(_require_strategy(call)),
                call.reason,
            )
        if call.method == "settleStrategyFee":
            return self._vault_contract.functions.settleStrategyFee(
                Web3.to_checksum_address(call.user),
                Web3.to_checksum_address(_require_strategy(call)),
            )
        if call.method == "rebalance":
            return self._vault_contract.functions.rebalance(
                Web3.to_checksum_address(call.user),
                [Web3.to_checksum_address(s) for s in call.strategies],
                [int(w) for w in call.weights_bps],
            )
        raise ValueError(f"unknown onchain method: {call.method}")


def _require_strategy(call: OnChainCall) -> str:
    if not call.strategy:
        raise ValueError(f"{call.method} requires a strategy address")
    return call.strategy


__all__ = ["OnChainCall", "OnChainRunner"]
