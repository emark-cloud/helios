"""LLMMomentumStrategy.on_bar — Claude-driven signal cases.

Mocks the Anthropic client so tests run offline with no API key.
Covers: LONG entry, EXIT on flip, low-confidence skip, HOLD action,
LONG-while-long no-op, malformed tool input, network error, no
tool_use block, insufficient history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from helios.types import Direction, MarketSnapshot
from llm_momentum_v1.strategy import LLMMomentumStrategy


def _snapshot(asset: str, *, prices: list[float]) -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset,
        timestamp=datetime.now(UTC),
        prices=prices,
        bar_interval_sec=60,
    )


class _FakeAnthropic:
    """Test double for `anthropic.Anthropic`.

    Records calls and returns a scripted response. Mimics the SDK's
    `client.messages.create(...) -> Response` shape with `.content`
    being a list of blocks; tool_use blocks carry `.type` and `.input`.
    """

    def __init__(
        self, tool_input: dict[str, Any] | None, *, raise_exc: Exception | None = None
    ) -> None:
        self._tool_input = tool_input
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []
        self.messages = self  # so `client.messages.create(...)` works

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._raise is not None:
            raise self._raise
        if self._tool_input is None:
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="no tool")])
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self._tool_input)])


def _strategy(client: Any, **kwargs: Any) -> LLMMomentumStrategy:
    s = LLMMomentumStrategy(
        signal_threshold=0.015,
        lookback_bars=5,
        position_fraction=0.5,
        client=client,
        **kwargs,
    )
    s.set_capital(10_000)
    return s


def test_long_when_claude_returns_long_high_confidence() -> None:
    client = _FakeAnthropic({"action": "LONG", "confidence": 0.8, "rationale": "uptrend"})
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])

    intent = s.on_bar("WETH", snap)

    assert intent is not None
    assert intent.direction == Direction.LONG
    assert intent.asset_in == "USDC"
    assert intent.asset_out == "WETH"
    assert intent.amount_in_usd is not None
    assert intent.amount_in_usd <= s.max_position_size_usd
    assert intent.is_nav_targeted is True
    assert len(client.calls) == 1


def test_exit_when_claude_returns_exit_while_long() -> None:
    client = _FakeAnthropic({"action": "EXIT", "confidence": 0.9, "rationale": "stalling"})
    s = _strategy(client)
    s.set_position("WETH", qty=0.5, avg_price=100.0, direction=Direction.LONG)
    snap = _snapshot("WETH", prices=[100.0, 99.5, 99.0, 98.5, 98.0, 97.5])

    intent = s.on_bar("WETH", snap)

    assert intent is not None
    assert intent.direction == Direction.EXIT
    assert intent.asset_in == "WETH"
    assert intent.asset_out == "USDC"
    assert intent.amount_in_asset == 0.5
    assert intent.is_signal_flip is True


def test_skip_on_low_confidence() -> None:
    client = _FakeAnthropic({"action": "LONG", "confidence": 0.3, "rationale": "weak"})
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    assert s.on_bar("WETH", snap) is None


def test_hold_action_skips() -> None:
    client = _FakeAnthropic({"action": "HOLD", "confidence": 0.95, "rationale": "wait"})
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    assert s.on_bar("WETH", snap) is None


def test_long_while_already_long_is_noop() -> None:
    client = _FakeAnthropic({"action": "LONG", "confidence": 0.9, "rationale": "keep going"})
    s = _strategy(client)
    s.set_position("WETH", qty=1.0, avg_price=100.0, direction=Direction.LONG)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    assert s.on_bar("WETH", snap) is None


def test_exit_while_flat_is_noop() -> None:
    client = _FakeAnthropic({"action": "EXIT", "confidence": 0.9, "rationale": "exit"})
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 99.5, 99.0, 98.5, 98.0, 97.5])
    assert s.on_bar("WETH", snap) is None


def test_malformed_tool_input_skips() -> None:
    client = _FakeAnthropic({"action": "BUY", "confidence": 0.9, "rationale": "x"})  # bad action
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    assert s.on_bar("WETH", snap) is None


def test_out_of_range_confidence_skips() -> None:
    client = _FakeAnthropic({"action": "LONG", "confidence": 1.5, "rationale": "x"})
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    assert s.on_bar("WETH", snap) is None


def test_no_tool_use_block_skips() -> None:
    client = _FakeAnthropic(None)  # returns text-only content
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    assert s.on_bar("WETH", snap) is None


def test_api_error_skips_gracefully() -> None:
    client = _FakeAnthropic(None, raise_exc=RuntimeError("network down"))
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    assert s.on_bar("WETH", snap) is None


def test_usdc_never_calls_claude() -> None:
    client = _FakeAnthropic({"action": "LONG", "confidence": 0.9, "rationale": "x"})
    s = _strategy(client)
    snap = _snapshot("USDC", prices=[1.0] * 6)
    assert s.on_bar("USDC", snap) is None
    assert client.calls == []  # short-circuit before the API call


def test_insufficient_history_skips_without_calling_claude() -> None:
    client = _FakeAnthropic({"action": "LONG", "confidence": 0.9, "rationale": "x"})
    s = _strategy(client)
    # lookback_bars=5 requires 6 prices; give only 4
    snap = _snapshot("WETH", prices=[100.0, 101.0, 102.0, 103.0])
    assert s.on_bar("WETH", snap) is None
    assert client.calls == []


def test_params_hash_matches_momentum_schema() -> None:
    """LLM strategy must produce a paramsHash bit-identical to the
    deterministic momentum strategy with the same bounds — that's
    what lets it reuse momentum_v1's on-chain registry slot."""
    from momentum_v1.strategy import MomentumStrategy

    llm = LLMMomentumStrategy(
        signal_threshold=0.015,
        max_slippage_bps=30,
        stop_loss_price=0.0,
    )
    det = MomentumStrategy(
        signal_threshold=0.015,
        max_slippage_bps=30,
        stop_loss_price=0.0,
    )
    assert llm.params_hash() == det.params_hash()


def test_default_asset_universe_unchanged() -> None:
    s = LLMMomentumStrategy(client=_FakeAnthropic(None))
    assert s.asset_universe == ("USDC", "WBTC", "WETH", "WSOL")


def test_asset_universe_override_accepted() -> None:
    s = LLMMomentumStrategy(client=_FakeAnthropic(None), asset_universe=("USDC", "WETH"))
    assert s.asset_universe == ("USDC", "WETH")


def test_asset_universe_must_start_with_usdc() -> None:
    with pytest.raises(ValueError, match="USDC"):
        LLMMomentumStrategy(client=_FakeAnthropic(None), asset_universe=("WETH", "USDC"))


def test_decision_call_includes_cache_control_and_tool_choice() -> None:
    """Regression: prompt caching + forced tool_choice must be wired."""
    client = _FakeAnthropic({"action": "HOLD", "confidence": 0.5, "rationale": "x"})
    s = _strategy(client)
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    s.on_bar("WETH", snap)

    assert len(client.calls) == 1
    kw = client.calls[0]
    # System prompt is sent as a list with cache_control.
    assert isinstance(kw["system"], list)
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Forced tool_choice on the decision tool.
    assert kw["tool_choice"] == {"type": "tool", "name": "decision"}
    assert kw["tools"][0]["name"] == "decision"
