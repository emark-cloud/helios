"""Stand-alone 90d yield-rotation backtest driver — kept as a runnable
worked example wrapping the SDK's `helios.run_yield_backtest`.

WS4: the SDK now exposes a yield-tick driver (`helios.backtest.
run_yield_backtest`). For YR strategies whose constructors require
arguments — like the reference impl — `helios backtest --strategy …`
cannot instantiate them with no args, so this harness still earns its
keep: it picks the constructor args for the reference strategy and
delegates the cadence + accounting to the SDK driver. Third-party
strategies with default-arg constructors should use `helios backtest`
directly.

Run from the repo root:
    uv run --project reference-strategies/yield_rotation_v1 \\
        python docs/backtests/_yield_rotation_v1_harness.py
"""

from __future__ import annotations

import math
import random

from helios import YieldTick, run_yield_backtest
from yield_rotation_v1 import YieldRotationStrategy

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
    ticks = [
        {
            m: YieldTick(
                market_id=m,
                apy_bps_e6=synth_apy_bps(seed, m, t),
                timestamp_ms=t * 3_600_000,
            )
            for m in MARKETS
        }
        for t in range(TICKS)
    ]
    report = run_yield_backtest(
        strategy=strategy,
        ticks=ticks,
        initial_capital=INITIAL_CAPITAL,
        tick_interval_sec=3_600,
        bridging_cost_bps=BRIDGING_COST_BPS,
    )
    return {
        "seed": seed,
        "rotations": len(report.rotations),
        "avg_active_apy_bps": round(report.avg_active_apy_bps, 1),
        "realized_yield_usd": round(report.realized_yield_usd, 2),
        "rotations_with_pos_diff": report.rotations_with_pos_diff,
        "median_diff_bps": round(report.median_apy_diff_bps, 1),
    }


_HEADER = (
    f"{'seed':>6} | {'rotations':>10} | {'avg_active_apy_bps':>20} | "
    f"{'realized_$':>12} | {'pos_diff':>10} | {'median_diff_bps':>16}"
)


def _format_row(r: dict[str, float | int]) -> str:
    return (
        f"{r['seed']:>6} | {r['rotations']:>10} | {r['avg_active_apy_bps']:>20} | "
        f"{r['realized_yield_usd']:>12} | {r['rotations_with_pos_diff']:>10} | "
        f"{r['median_diff_bps']:>16}"
    )


def main() -> None:
    print(_HEADER)
    for seed in (17, 42, 101, 314, 7331):
        print(_format_row(run(seed)))


if __name__ == "__main__":
    main()
