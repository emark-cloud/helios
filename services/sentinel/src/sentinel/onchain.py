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
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from sentinel.state import AllocationState

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OnChainCall:
    """A planned chain call. The runner either submits or records it."""

    method: str
    user: str
    strategy: str | None
    amount: int = 0
    reason: str = ""
    weights_bps: tuple[int, ...] = ()
    strategies: tuple[str, ...] = ()


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
        falls back to its in-memory mirror. The real implementation
        (web3.py call to `AllocatorVault.allocationOf` + `StrategyVault.
        navOf`) lands in WS3 once contract addresses are wired.
        """
        if not self._live:
            return None
        del user, strategy  # arguments will be wired through to web3 calls in WS3
        raise NotImplementedError("live AllocatorVault reads are wired in WS3 e2e")

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
        # WS3: encode + sign + submit. Tracked in TODO.md WS2.C gate
        # ("Auto-defund test passes"). Until contract addresses are in
        # `kite-testnet.json`, this branch is unreachable.
        raise NotImplementedError("live tx submission lands in WS3 e2e")
