"""Slice timestamped events into 7d / 30d / 90d windows.

Pure helper. Inputs are sequences of objects with a `timestamp` attribute (unix
seconds); outputs are three lists, each containing the events whose timestamp
falls within the corresponding window relative to `now_unix`. The 7d window is
a strict subset of 30d, which is a strict subset of 90d.

Used by the score formula (`reputation.score`) which computes cohort-relative
Sharpes per window per `Helios.md §8.2`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

DAY_SEC = 24 * 60 * 60
WINDOW_DAYS: tuple[int, ...] = (7, 30, 90)


class _Timestamped(Protocol):
    @property
    def timestamp(self) -> int: ...


T = TypeVar("T", bound=_Timestamped)


@dataclass(frozen=True, slots=True)
class WindowedEvents(Generic[T]):
    last_7d: list[T]
    last_30d: list[T]
    last_90d: list[T]

    def by_days(self, days: int) -> list[T]:
        if days == 7:
            return self.last_7d
        if days == 30:
            return self.last_30d
        if days == 90:
            return self.last_90d
        raise ValueError(f"unsupported window: {days}d")


def slice_windows(events: Sequence[T], now_unix: int) -> WindowedEvents[T]:
    cutoff_7d = now_unix - 7 * DAY_SEC
    cutoff_30d = now_unix - 30 * DAY_SEC
    cutoff_90d = now_unix - 90 * DAY_SEC
    last_7d: list[T] = []
    last_30d: list[T] = []
    last_90d: list[T] = []
    for e in events:
        ts = e.timestamp
        if ts >= cutoff_90d:
            last_90d.append(e)
            if ts >= cutoff_30d:
                last_30d.append(e)
                if ts >= cutoff_7d:
                    last_7d.append(e)
    return WindowedEvents(last_7d=last_7d, last_30d=last_30d, last_90d=last_90d)
