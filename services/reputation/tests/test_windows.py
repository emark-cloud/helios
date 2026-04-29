"""Window slicing — boundary inclusion + monotonic nesting (7d ⊂ 30d ⊂ 90d)."""

from __future__ import annotations

from dataclasses import dataclass

from reputation.windows import DAY_SEC, slice_windows


@dataclass(frozen=True, slots=True)
class _Ev:
    timestamp: int


_NOW = 1_700_000_000


def _ev_days_ago(d: float) -> _Ev:
    return _Ev(timestamp=_NOW - int(d * DAY_SEC))


def test_empty_input() -> None:
    w = slice_windows([], _NOW)
    assert w.last_7d == []
    assert w.last_30d == []
    assert w.last_90d == []


def test_each_window_is_subset_of_the_next() -> None:
    events = [_ev_days_ago(d) for d in (0.5, 6.9, 7.1, 29.9, 30.1, 89.9, 90.1, 365)]
    w = slice_windows(events, _NOW)
    assert {e.timestamp for e in w.last_7d}.issubset({e.timestamp for e in w.last_30d})
    assert {e.timestamp for e in w.last_30d}.issubset({e.timestamp for e in w.last_90d})


def test_boundary_inclusive() -> None:
    on_boundary = [_Ev(timestamp=_NOW - 7 * DAY_SEC), _Ev(timestamp=_NOW - 30 * DAY_SEC)]
    w = slice_windows(on_boundary, _NOW)
    assert len(w.last_7d) == 1
    assert len(w.last_30d) == 2


def test_events_outside_90d_dropped() -> None:
    w = slice_windows([_ev_days_ago(91), _ev_days_ago(365)], _NOW)
    assert w.last_7d == w.last_30d == w.last_90d == []


def test_by_days_dispatch() -> None:
    events = [_ev_days_ago(1), _ev_days_ago(20), _ev_days_ago(60)]
    w = slice_windows(events, _NOW)
    assert len(w.by_days(7)) == 1
    assert len(w.by_days(30)) == 2
    assert len(w.by_days(90)) == 3
