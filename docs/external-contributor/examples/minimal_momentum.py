"""Minimal external-contributor strategy fixture.

Smallest StrategyAgent subclass that exercises `helios backtest` and
`helios simulate` end-to-end. Mirrors the operator-guide §1 example
verbatim — the smoke acceptance is "what we tell users to copy works."

This module is only ever loaded inside the smoke Docker image, where
`helios-strategy-sdk` is pip-installed. The repo-level pyright config
excludes `docs/`, but the IDE LSP doesn't — silence the false positive
so contributors copying this file don't see a phantom error.
"""

# pyright: reportMissingImports=false

from __future__ import annotations

from helios import Direction, MarketSnapshot, StrategyAgent, TradeIntent


class MinimalMomentum(StrategyAgent):
    declared_class = "momentum_v1"
    asset_universe = ("USDC", "WKITE", "WETH")
    max_position_size_usd = 5_000
    fee_rate_bps = 2_000  # 20% perf fee above HWM

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        if asset == "USDC":
            return None
        ret = snapshot.return_over(bars=10)
        position = self.position_for(asset)
        if ret > 0.015 and position <= 0:
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_usd=min(self.max_position_size_usd, self.available_capital * 0.5),
                direction=Direction.LONG,
                max_slippage_bps=30,
            )
        if ret < -0.015 and position > 0:
            return TradeIntent(
                asset_in=asset,
                asset_out="USDC",
                amount_in_asset=position,
                direction=Direction.EXIT,
                max_slippage_bps=30,
            )
        return None
