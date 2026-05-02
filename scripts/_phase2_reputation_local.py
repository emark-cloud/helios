"""WS6 PR3.B — local reputation engine driver.

The shipped `services/reputation` engine queries Goldsky via the
`_GoldskyProto` Protocol. For the e2e we don't need a full subgraph
deployment — we synthesize the same `StrategyState` shape directly
from on-chain event logs.

`LocalGoldskyStub` implements the protocol:

  - `trades_attested`: number of `TradeAttested` events (momentum +
    mean-rev) plus `YieldRotationAttested` events (yield-rotation)
    emitted by the vault.
  - `nav_snapshots_90d`: `NAVReported` events emitted by the vault,
    filtered by `event.timestamp >= since_unix`.
  - `trades_90d`: same source as `trades_attested`, also filtered by
    `since_unix`.
  - `stake_e18` / `declared_class`: read from
    `StrategyRegistry.strategies(vault)`.
  - `capital_deployed_e18`: synthesized from `AllocationCreated` event
    capital (mirrors the Goldsky aggregation).

The engine consumes this stub and runs `tick_once(now_unix=...)` for
the PR3.B assertion bundle.
"""

from __future__ import annotations

from dataclasses import dataclass

from reputation.goldsky import NavEvent, StrategyState, TradeEvent
from web3 import Web3
from web3.contract.contract import Contract


@dataclass
class _VaultRegistration:
    address: str
    declared_class_hex: str  # 0x-prefixed bytes32
    stake_e18: int


def _strategy_record(registry: Contract, vault_address: str) -> _VaultRegistration:
    """Read `StrategyRegistry.strategyOf(vault)` and normalize.

    Tuple shape from `IStrategyRegistry.StrategyEntry`:
        (vault, operator, declaredClass, stakeAmount, currentReputation,
         registeredAt, active)
    """
    rec = registry.functions.strategyOf(Web3.to_checksum_address(vault_address)).call()
    declared_class = rec[2]
    if isinstance(declared_class, (bytes, bytearray)):
        declared_class_hex = "0x" + bytes(declared_class).hex()
    else:
        declared_class_hex = str(declared_class)
    stake_e18 = int(rec[3])  # USDC = 6 decimals; engine normalizes by /1e18
    return _VaultRegistration(
        address=Web3.to_checksum_address(vault_address),
        declared_class_hex=declared_class_hex,
        stake_e18=stake_e18,
    )


class LocalGoldskyStub:
    """Implements `_GoldskyProto` against on-chain logs.

    Filtered to `since_unix` per the protocol contract. The engine slices
    the returned 90d events into 7d/30d/90d windows internally.
    """

    def __init__(
        self,
        *,
        w3: Web3,
        registry: Contract,
        allocator_vault: Contract,
        strategy_vaults: list[Contract],
        from_block: int,
    ) -> None:
        self._w3 = w3
        self._registry = registry
        self._allocator_vault = allocator_vault
        self._vaults = strategy_vaults
        self._from_block = from_block

    async def fetch_strategy_states(self, since_unix: int) -> list[StrategyState]:
        states: list[StrategyState] = []
        for vault in self._vaults:
            reg = _strategy_record(self._registry, vault.address)

            nav_logs = list(
                vault.events.NAVReported.get_logs(
                    from_block=self._from_block, to_block="latest"
                )
            )
            trade_logs = list(
                vault.events.TradeAttested.get_logs(
                    from_block=self._from_block, to_block="latest"
                )
            )
            yr_logs = list(
                vault.events.YieldRotationAttested.get_logs(
                    from_block=self._from_block, to_block="latest"
                )
            )

            nav_events: list[NavEvent] = []
            for ev in nav_logs:
                ts = int(ev["args"]["timestamp"])
                if ts >= since_unix:
                    nav_events.append(
                        NavEvent(timestamp=ts, total_nav_e18=int(ev["args"]["totalNAV"]))
                    )

            trade_events: list[TradeEvent] = []
            for ev in trade_logs:
                # `TradeAttested` doesn't carry a unix timestamp; use the
                # block ts. Phase 2 events fire close to wall-clock since
                # anvil mines at 1s/block in the e2e.
                block = self._w3.eth.get_block(ev["blockNumber"])
                ts = int(block["timestamp"])
                if ts >= since_unix:
                    trade_events.append(
                        TradeEvent(
                            timestamp=ts,
                            proof_valid=True,  # event only emits on verify success
                            amount_in_e18=int(ev["args"]["amountIn"]),
                        )
                    )
            for ev in yr_logs:
                block = self._w3.eth.get_block(ev["blockNumber"])
                ts = int(block["timestamp"])
                if ts >= since_unix:
                    trade_events.append(
                        TradeEvent(
                            timestamp=ts,
                            proof_valid=True,
                            amount_in_e18=int(ev["args"]["amountRotating"]),
                        )
                    )
            trades_attested = len(trade_logs) + len(yr_logs)

            # Capital deployed via AllocationCreated for THIS vault.
            alloc_logs = list(
                self._allocator_vault.events.AllocationCreated.get_logs(
                    from_block=self._from_block, to_block="latest"
                )
            )
            capital = 0
            vault_lower = vault.address.lower()
            for ev in alloc_logs:
                if str(ev["args"]["strategy"]).lower() == vault_lower:
                    capital += int(ev["args"]["amount"])

            states.append(
                StrategyState(
                    strategy_id=vault.address,
                    declared_class=reg.declared_class_hex,
                    stake_e18=reg.stake_e18,
                    trades_attested=trades_attested,
                    capital_deployed_e18=capital,
                    trades_90d=sorted(trade_events, key=lambda e: e.timestamp),
                    nav_snapshots_90d=sorted(nav_events, key=lambda e: e.timestamp),
                )
            )
        return states

    async def aclose(self) -> None:  # pragma: no cover — nothing to close
        return None


__all__ = ["LocalGoldskyStub"]
