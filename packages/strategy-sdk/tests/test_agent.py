"""Tests for the StrategyAgent base class."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from helios import (
    Direction,
    MarketSnapshot,
    Position,
    StrategyAgent,
    TradeIntent,
)


class _NoopAgent(StrategyAgent):
    declared_class = "momentum_v1"
    asset_universe = ("USDC", "WETH")
    max_position_size_usd = 1_000
    fee_rate_bps = 2_000

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        return None


def _snapshot(asset: str = "WETH") -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset, timestamp=datetime.now(UTC), prices=[100.0, 101.0], bar_interval_sec=60
    )


def test_declared_class_required() -> None:
    class Bad(StrategyAgent):
        def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
            return None

    with pytest.raises(RuntimeError, match="declared_class"):
        Bad()


def test_size_trade_uses_intent_amount_clamped_by_cap() -> None:
    a = _NoopAgent()
    intent = TradeIntent(
        asset_in="USDC", asset_out="WETH", amount_in_usd=5_000, direction=Direction.LONG
    )
    # Capped by max_position_size_usd (1_000) even when intent asks for 5_000.
    assert a.size_trade(intent, available_capital=10_000) == 1_000.0


def test_size_trade_clamped_by_available_capital() -> None:
    a = _NoopAgent()
    intent = TradeIntent(
        asset_in="USDC", asset_out="WETH", amount_in_usd=900, direction=Direction.LONG
    )
    assert a.size_trade(intent, available_capital=500) == 500.0


def test_size_trade_zero_when_only_asset_amount_provided() -> None:
    # Without a price, the SDK can't safely convert asset → USD; default
    # returns zero so the backtest engine treats the intent as a no-op.
    a = _NoopAgent()
    intent = TradeIntent(
        asset_in="WETH", asset_out="USDC", amount_in_asset=0.5, direction=Direction.EXIT
    )
    assert a.size_trade(intent, available_capital=10_000) == 0.0


def test_should_exit_default_is_false() -> None:
    a = _NoopAgent()
    pos = Position(asset="WETH", quantity=1.0, avg_entry_price=100.0, direction=Direction.LONG)
    assert a.should_exit("WETH", _snapshot(), pos) is False


def test_position_object_round_trip() -> None:
    a = _NoopAgent()
    a._set_position("WETH", 2.0, 100.0, Direction.LONG)
    pos = a.position_object("WETH")
    assert pos is not None and pos.quantity == 2.0
    a._set_position("WETH", 0.0, 0.0, Direction.EXIT)
    assert a.position_object("WETH") is None


def test_manifest_passes_through_class_attributes() -> None:
    a = _NoopAgent()
    m = a.manifest(operator="0xabc", stake_amount_usd=5_000, max_capacity_usd=100_000)
    assert m.declared_class == "momentum_v1"
    assert m.fee_rate_bps == 2_000
    assert m.stake_amount_usd == 5_000
    assert m.max_capacity_usd == 100_000
