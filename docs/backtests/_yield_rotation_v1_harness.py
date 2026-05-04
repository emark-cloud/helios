"""Stand-alone 90d yield-rotation backtest harness.

The SDK's bar-driven backtest engine doesn't call `on_yield_tick`
(yield is a different cadence than price). This harness drives it
directly with synthetic APY traces so we can produce the
`docs/backtests/yield_rotation_v1_90d.md` numbers.

Run from the repo root:
    uv run --no-sync python /tmp/yr_harness.py
"""

from __future__ import annotations

import math
import random

from yield_rotation_v1 import YieldRotationStrategy
from yield_rotation_v1.types import YieldTick

TICKS_PER_DAY = 24
DAYS = 90
TICKS = TICKS_PER_DAY * DAYS
MARKETS = (1, 2, 3, 4)
BASE_APY_BPS = {1: 380, 2: 420, 3: 510, 4: 290}  # initial APYs in bps
INITIAL_CAPITAL = 50_000.0
SIGNAL_THRESHOLD_BPS = 80
BRIDGING_COST_BPS = 30


def synth_apy_bps(seed: int, market: int, tick: int) -> int:
    """Per-market APY trajectory: base + slow drift + noise + occasional jump."""
    rng = random.Random(seed * 10_000 + market * 1_000 + tick)
    base = BASE_APY_BPS[market]
    drift = 30 * math.sin(tick / (TICKS_PER_DAY * 14) + market)  # ~14d cycle
    noise = rng.uniform(-15, 15)
    jump = rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 50, -50, 100, -75])  # tail events
    return max(0, int((base + drift + noise + jump) * 1_000_000))


def run(seed: int) -> dict[str, float | int]:
    strategy = YieldRotationStrategy(
        allowlisted_markets=MARKETS,
        signal_threshold_bps=SIGNAL_THRESHOLD_BPS,
        bridging_cost_bps=BRIDGING_COST_BPS,
    )
    strategy.set_capital(INITIAL_CAPITAL)
    rotations: list[tuple[int, int, int, int]] = []
    realized_yield_bps_ticks = 0  # Σ (apy_active_bps × dt_in_ticks)

    for tick in range(TICKS):
        ticks_now = {
            m: YieldTick(
                market_id=m,
                apy_bps_e6=synth_apy_bps(seed, m, tick),
                timestamp_ms=tick * 3_600_000,
            )
            for m in MARKETS
        }
        active = strategy._active_market  # type: ignore[attr-defined]
        if active is not None and active in ticks_now:
            apy = ticks_now[active].apy_bps_e6 // 1_000_000
            realized_yield_bps_ticks += apy
        intent = strategy.on_yield_tick(ticks_now)
        if intent is not None:
            rotations.append(
                (tick, intent.m_from, intent.m_to, intent.apy_to_bps - intent.apy_from_bps)
            )
            strategy.set_active_market(intent.m_to)

    # Convert ticks-of-bps into annualised return: each tick is 1 hour;
    # APY is annual, so per-tick contribution is apy_bps / (365*24).
    apy_avg_bps = realized_yield_bps_ticks / TICKS if TICKS else 0
    return {
        "seed": seed,
        "rotations": len(rotations),
        "avg_active_apy_bps": round(apy_avg_bps, 1),
        "rotations_with_pos_diff": sum(1 for r in rotations if r[3] > 0),
        "median_diff_bps": _median([r[3] for r in rotations]) if rotations else 0,
    }


def _median(xs: list[int]) -> float:
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(xs[n // 2])
    return (xs[n // 2 - 1] + xs[n // 2]) / 2.0


_HEADER = (
    f"{'seed':>6} | {'rotations':>10} | {'avg_active_apy_bps':>20} | "
    f"{'pos_diff':>10} | {'median_diff_bps':>16}"
)


def _format_row(r: dict[str, float | int]) -> str:
    return (
        f"{r['seed']:>6} | {r['rotations']:>10} | {r['avg_active_apy_bps']:>20} | "
        f"{r['rotations_with_pos_diff']:>10} | {r['median_diff_bps']:>16}"
    )


def main() -> None:
    print(_HEADER)
    for seed in (17, 42, 101, 314, 7331):
        print(_format_row(run(seed)))


if __name__ == "__main__":
    main()
