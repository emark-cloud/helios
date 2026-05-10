"""AllocatorOnChain — the SDK's chain client.

Three responsibilities:

1. Read live state from the AllocatorVault + StrategyVault that Goldsky
   doesn't yet surface fast enough — `AllocatorVault.allocationOf(user,
   strategy)` (capital deployed + HWM + defundedAt) and
   `StrategyVault.navOf(allocatorVault)` (current NAV share).
2. Submit the four operator-driven calls: `allocateToStrategy`,
   `defundStrategy`, `rebalance`, `settleStrategyFee`.
3. Register the allocator on `AllocatorRegistry` with its supported
   classes / fee rate / stake amount. Callable once at boot via
   `register_allocator(...)` — third-party allocators built from
   `helios-allocator init` invoke this from a one-shot CLI step.

Address-gated: when `allocator_vault_address` is unset, the runner is a
no-op that records what it *would have* done. Same posture as the
reputation engine's `REPUTATION_ANCHOR_ADDRESS` gate. Sentinel and
Helix both rely on this for scenario / dry-run / unit-test paths.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog
from eth_account import Account
from helios_contracts_abi.abis import IAllocatorRegistry_ABI, IAllocatorVault_ABI
from web3 import Web3
from web3.types import TxReceipt

from helios_allocator.runtime.state import AllocationState

# 30s mirrors `services/_template/src/_template/web3_consts.RECEIPT_TIMEOUT_SEC`.
# Inlined here to keep the SDK free of workspace-only runtime dependencies
# (the SDK ships to PyPI; `_template` does not). See
# `project_strategy_sdk_distribution.md` memory.
RECEIPT_TIMEOUT_SEC: int = 30

# Minimal balanceOf fragment for UserVault. The generated `IUserVault_ABI`
# in `helios-contracts-abi-py` only ships the operator-facing surface
# (deposit/setMetaStrategy/delegateToAllocator/withdraw + events), not
# the per-user balance accessor. Inlining here avoids a binding-regen
# cycle for a single read-only call. Signature matches
# `UserVault.balanceOf(address)` in `contracts/src/UserVault.sol:279`.
_USER_VAULT_BALANCE_ABI: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
)

_log = structlog.get_logger(__name__)


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


class AllocatorOnChain:
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
        user_vault_address: str = "",
    ) -> None:
        self._rpc_url = rpc_url
        self._operator_pk = operator_pk
        self._allocator_vault = allocator_vault_address
        self._allocator_registry = allocator_registry_address
        self._user_vault = user_vault_address
        self._chain_id = chain_id
        self._live = bool(rpc_url and operator_pk and allocator_vault_address)
        self.pending: list[OnChainCall] = []

        # Live-mode handles initialised lazily on first submit so dry-run
        # tests don't need to spin up an RPC client.
        self._w3: Web3 | None = None
        self._account: Any = None
        self._vault_contract: Any = None
        self._registry_contract: Any = None
        self._user_vault_contract: Any = None

    @property
    def live(self) -> bool:
        return self._live

    @property
    def allocator_vault(self) -> str:
        return self._allocator_vault

    @property
    def allocator_registry(self) -> str:
        return self._allocator_registry

    @property
    def user_vault(self) -> str:
        return self._user_vault

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

    # ── Async wrappers ────────────────────────────────────────
    # Each `_submit` ends in `wait_for_transaction_receipt(timeout=30)`.
    # Used directly from the async decision loop, that freezes the event
    # loop — every WS subscriber and the drawdown-poll cadence stall for
    # up to 30s per emitted call. The async variants run the sync path
    # on a worker thread (mirroring `oracle/anchor.AnchorPoster.post_async`)
    # so the loop keeps draining while a single tx waits for its receipt.

    async def allocate_async(self, user: str, strategy: str, amount: int) -> OnChainCall:
        return await asyncio.to_thread(self.allocate, user, strategy, amount)

    async def defund_async(self, user: str, strategy: str, reason: str) -> OnChainCall:
        return await asyncio.to_thread(self.defund, user, strategy, reason)

    async def rebalance_async(
        self,
        user: str,
        strategies: list[str],
        weights_bps: list[int],
    ) -> OnChainCall:
        return await asyncio.to_thread(self.rebalance, user, strategies, weights_bps)

    async def settle_fee_async(self, user: str, strategy: str) -> OnChainCall:
        return await asyncio.to_thread(self.settle_fee, user, strategy)

    def read_user_vault_balance(self, user: str) -> int | None:
        """Idle UserVault balance for `user`, in raw asset wei.

        Returns None when stub mode is active or `user_vault_address` is
        unset — the loop falls back to its in-memory `delegated_capital_usd`
        in that case (which tests seed manually). Live mode reads
        `UserVault.balanceOf(user)`. The unit is raw asset wei (18 dec
        for the deployed mUSDC mock); `_apply_diffs` passes the same
        units straight to `allocateToStrategy`, so no conversion is
        needed.
        """
        if not self._live or not self._user_vault:
            return None
        self._ensure_live()
        assert self._w3 is not None
        if self._user_vault_contract is None:
            self._user_vault_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(self._user_vault),
                abi=list(_USER_VAULT_BALANCE_ABI),
            )
        balance = self._user_vault_contract.functions.balanceOf(
            Web3.to_checksum_address(user)
        ).call()
        return int(balance)

    async def read_user_vault_balance_async(self, user: str) -> int | None:
        return await asyncio.to_thread(self.read_user_vault_balance, user)

    async def read_allocation(self, user: str, strategy: str) -> AllocationState | None:
        """Mirror current on-chain allocation state.

        Stub mode returns None; the loop falls back to its in-memory
        mirror. Live mode reads `AllocatorVault.allocationOf(user, strategy)`.
        """
        if not self._live:
            return None
        self._ensure_live()
        assert self._vault_contract is not None
        record = self._vault_contract.functions.allocationOf(
            Web3.to_checksum_address(user), Web3.to_checksum_address(strategy)
        ).call()
        # Tuple matches IAllocatorVault.AllocationRecord.
        # record[0]=strategy, [1]=capitalDeployed, [2]=highWaterMark,
        # [3]=defundedAt, [4]=lastUpdate.
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

    # ── Allocator registration ───────────────────────────────
    def register_allocator(
        self,
        name: str,
        ranking_function_hash: bytes,
        supported_classes: list[bytes],
        fee_rate_bps: int,
        stake_amount: int,
    ) -> str:
        """One-shot: register this allocator on `AllocatorRegistry`.

        Returns the allocator address (operator vault) registered.
        Stub mode is a no-op returning the configured vault. Live mode
        submits `AllocatorRegistry.registerAllocator(...)` and waits for
        a receipt.

        The reserved-name check (`"Helios Sentinel"` / `"Helios Helix"`)
        is enforced on-chain — registering with a reserved name reverts.
        Third parties spawn this call from `helios-allocator init`'s
        scaffolded `register` command.
        """
        if not self._live:
            _log.info(
                "allocator.onchain.register.dry_run",
                name=name,
                fee_rate_bps=fee_rate_bps,
                stake_amount=stake_amount,
            )
            return self._allocator_vault
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        if self._registry_contract is None:
            if not self._allocator_registry:
                raise RuntimeError("allocator_registry_address required for register_allocator")
            self._registry_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(self._allocator_registry),
                abi=IAllocatorRegistry_ABI,
            )
        fn = self._registry_contract.functions.registerAllocator(
            name,
            Web3.to_checksum_address(self._allocator_vault),
            ranking_function_hash,
            supported_classes,
            int(fee_rate_bps),
            int(stake_amount),
        )
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
                "chainId": self._chain_id,
                "gasPrice": self._w3.eth.gas_price,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"registerAllocator reverted: {tx_hash.hex()}")
        _log.info(
            "allocator.onchain.register.submitted",
            name=name,
            tx_hash=tx_hash.hex(),
            block=receipt["blockNumber"],
        )
        return self._allocator_vault

    def _submit(self, call: OnChainCall) -> OnChainCall:
        if not self._live:
            self.pending.append(call)
            _log.info(
                "allocator.onchain.dry_run",
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
                "allocator.onchain.submit_failed",
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
        try:
            self._account = Account.from_key(self._operator_pk)
        except Exception as exc:  # pragma: no cover — defensive
            # Don't let the raised value (which may include the malformed key
            # material) propagate up into structlog or a stack trace.
            raise RuntimeError(f"invalid OPERATOR_PK: {type(exc).__name__}") from None
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
            tx_hash, timeout=RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"tx reverted: {call.tx_hash}")
        call.submitted = True
        _log.info(
            "allocator.onchain.submitted",
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


__all__ = ["AllocatorOnChain", "OnChainCall"]
