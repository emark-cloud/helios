"""WS5.B — `_parse_allocator` unit tests against the WS5.B subgraph schema.

The query in `goldsky.py` reads the `Allocator → delegations + decisions`
shape; this test pins the parser's aggregation rules so a future schema
tweak doesn't silently shift the engine's allocator inputs.
"""

from __future__ import annotations

from reputation.goldsky import _parse_allocator

_WINDOW_START = 1_700_000_000
_NOW = _WINDOW_START + 30 * 24 * 60 * 60


def _delegation(*, capital: int, since: int, defunded_at: int = 0) -> dict[str, object]:
    return {"capital": str(capital), "since": str(since), "defundedAt": str(defunded_at)}


def _decision(*, ts: int, reason: str) -> dict[str, object]:
    return {"id": "0xff", "timestamp": str(ts), "reason": reason}


def test_active_delegations_aggregate_capital_and_count_users() -> None:
    raw = {
        "id": "0xa1",
        "stakeAmount": "1000",
        "delegations": [
            _delegation(capital=10**18, since=_WINDOW_START - 100),
            _delegation(capital=2 * 10**18, since=_WINDOW_START - 50),
        ],
        "decisions": [],
    }
    s = _parse_allocator(raw, _WINDOW_START)
    assert s.aggregate_capital_e18 == 3 * 10**18
    assert s.users_at_window_end == 2
    assert s.users_at_window_start == 2


def test_defunded_delegations_excluded_from_active_capital() -> None:
    raw = {
        "id": "0xa2",
        "stakeAmount": "0",
        "delegations": [
            _delegation(capital=10**18, since=_WINDOW_START - 100),
            _delegation(
                capital=5 * 10**18,
                since=_WINDOW_START - 200,
                defunded_at=_WINDOW_START + 1000,
            ),
        ],
        "decisions": [],
    }
    s = _parse_allocator(raw, _WINDOW_START)
    # Only the active delegation counts toward live capital + retention end.
    assert s.aggregate_capital_e18 == 10**18
    assert s.users_at_window_end == 1
    # Both delegations existed at window start (defund happened later).
    assert s.users_at_window_start == 2


def test_delegation_lifecycle_inside_window_excluded_from_retention_start() -> None:
    """A user who delegated AND defunded within the window contributes
    to neither retention numerator nor denominator — there's nothing to
    retain because they weren't there at window start."""
    raw = {
        "id": "0xa3",
        "stakeAmount": "0",
        "delegations": [
            _delegation(
                capital=10**18,
                since=_WINDOW_START + 100,
                defunded_at=_WINDOW_START + 200,
            ),
        ],
        "decisions": [],
    }
    s = _parse_allocator(raw, _WINDOW_START)
    assert s.users_at_window_start == 0
    assert s.users_at_window_end == 0


def test_drawdown_reason_decisions_count_as_breaches() -> None:
    raw = {
        "id": "0xa4",
        "stakeAmount": "0",
        "delegations": [],
        "decisions": [
            _decision(ts=_NOW - 1000, reason="DRAWDOWN_THRESHOLD_BREACHED"),
            _decision(ts=_NOW - 500, reason="max_drawdown"),
            _decision(ts=_NOW - 100, reason="rebalance"),  # excluded
        ],
    }
    s = _parse_allocator(raw, _WINDOW_START)
    # Two drawdown-flavored defunds → breach_total + breach_response = 2
    # (placeholder: every observed defund is treated as responded until
    # WS3.A's per-trade P&L pairs breach with NAV-crossover timing).
    assert s.breach_total_count == 2
    assert s.breach_response_count == 2


def test_pnl_above_hwm_is_zero_until_ws3a_lands() -> None:
    """Until per-trade P&L emission ships, the parser feeds 0 — the
    engine's PnL component collapses to 0 and allocators are
    differentiated on retention + drawdown + stake."""
    raw = {
        "id": "0xa5",
        "stakeAmount": "0",
        "delegations": [_delegation(capital=10**18, since=_WINDOW_START - 1)],
        "decisions": [],
    }
    s = _parse_allocator(raw, _WINDOW_START)
    assert s.aggregate_pnl_above_hwm_e18 == 0


def test_missing_optional_fields_default_safely() -> None:
    """Goldsky returns `None` (not 0) for unset BigInt / nullable fields.
    The parser must coerce safely so a thin/malformed payload doesn't
    crash the engine tick."""
    raw = {"id": "0xa6"}
    s = _parse_allocator(raw, _WINDOW_START)
    assert s.allocator_id == "0xa6"
    assert s.stake_e18 == 0
    assert s.aggregate_capital_e18 == 0
    assert s.users_at_window_end == 0
    assert s.users_at_window_start == 0
    assert s.breach_total_count == 0
