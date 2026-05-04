"""WS6 — phase2-multi-class scenario generator.

Run `python scenarios/_generate_phase2.py` to (re)write
`scenarios/phase2-multi-class.json`.

The fixture seeds the Phase 2 e2e scenario (`scripts/e2e_scenario_phase2.py`)
with a 200-bar, three-asset price replay. One bar = 60_000 ms walltime;
the narrative compresses 90 days but the oracle replays at its own
cadence — the timestamps below are ordinal, not calendar.

Series shape (each tuned to give one strategy class a clean signal):

  KITE/USDT — momentum + mean-reversion + auto-defund. $1.50 → $1.75 over
  bars 0..70 (clean uptrend for momentum_v1 to ride), then $1.75 → $1.20
  over bars 70..150 (>30% drawdown — this is the leg that exercises the
  permissionless-defund hard gate per Helios.md §6.3 against any strategy
  caught long the top), then $1.20 → $1.45 over bars 150..200 (recovery
  re-baselines reputation cohort math).

  ETH/USDT — mean-reversion. Sinusoidal around $3200 with deep dips at
  bars 50, 110, 170 (~6% below the 30-bar MA each) — clean n-sigma
  triggers for mean_reversion_v1 to enter, plus a steady-state baseline
  in between. Amplitude is small enough that momentum_v1 stays out.

  BTC/USDT — smooth high-conviction momentum. $65k → $72k linear over
  200 bars; no drawdowns. Used by the second momentum variant to give
  the cohort a divergence signal (variant 1 trades KITE and eats the
  drawdown; variant 2 trades BTC and rides clean).

Yields are NOT in this file — the Aave/Compound stub yield sources at
`services/oracle/src/oracle/sources/yield_*_stub.py` carry their own
tick series. WS6 PR2 extends scenario.py to optionally pull yield ticks
from a `yields` block here so YR strategies have 200-bar scripts to
chase, but PR1 leaves yields on the built-in stubs (which clamp at the
last tick after 6 calls — fine for skeleton plumbing, not for a 90-day
replay).

Re-running this generator is deterministic: the math has no RNG.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────

BARS = 200
BAR_MS = 60_000  # 1-minute bars (matches Phase 1 fixture cadence)
WAD = 10**18  # price_e18 scaling


def _to_wad(price_usd: float) -> str:
    """Float USD → e18 string. Round to integer wei."""
    return str(int(round(price_usd * WAD)))


# ── Series builders ────────────────────────────────────────────────


def _kite_series() -> list[dict[str, str | int]]:
    """KITE: ramp 1.50→1.75 (0..70), drawdown 1.75→1.20 (70..150), recovery (150..200)."""
    out = []
    for i in range(BARS):
        if i <= 70:
            # Ramp up
            t = i / 70
            price = 1.50 + (1.75 - 1.50) * t
        elif i <= 150:
            # Drawdown
            t = (i - 70) / (150 - 70)
            price = 1.75 + (1.20 - 1.75) * t
        else:
            # Recovery
            t = (i - 150) / (BARS - 150)
            price = 1.20 + (1.45 - 1.20) * t
        # Light noise so the moving-average smoother doesn't degenerate.
        # Deterministic: small sinusoid keyed by bar index.
        price += 0.005 * math.sin(i * 0.7)
        out.append({"ts_ms": i * BAR_MS, "price_e18": _to_wad(price)})
    return out


def _eth_series() -> list[dict[str, str | int]]:
    """ETH: oscillates ~$3200 ± $40 with three sharp dip clusters."""
    dip_centers = (50, 110, 170)
    out = []
    for i in range(BARS):
        # Baseline sinusoid (period ~30 bars).
        base = 3200.0 + 40.0 * math.sin(i * 2 * math.pi / 30)
        # Deep dip if within ±2 bars of a dip center.
        dip = 0.0
        for c in dip_centers:
            if abs(i - c) <= 2:
                # ~6% drop tapered Gaussian-ish.
                dip += -190.0 * math.exp(-((i - c) ** 2) / 1.5)
        out.append({"ts_ms": i * BAR_MS, "price_e18": _to_wad(base + dip)})
    return out


def _btc_series() -> list[dict[str, str | int]]:
    """BTC: clean linear uptrend $65_000 → $72_000 with mild noise."""
    out = []
    for i in range(BARS):
        t = i / (BARS - 1)
        price = 65_000.0 + (72_000.0 - 65_000.0) * t
        price += 25.0 * math.sin(i * 0.4)  # tiny wiggle
        out.append({"ts_ms": i * BAR_MS, "price_e18": _to_wad(price)})
    return out


# ── Driver ─────────────────────────────────────────────────────────


def main() -> None:
    fixture = {
        "name": "phase2-multi-class",
        "description": (
            "Phase 2 e2e (WS6). 200 bars × 3 assets across 90d compressed. "
            "KITE rallies then draws down >30% then recovers (momentum entry, "
            "mean-rev opportunity, auto-defund trigger). ETH oscillates with "
            "deep n-sigma dips at bars 50/110/170 (mean-reversion signal). "
            "BTC trends linearly upward (clean momentum, no drawdown — "
            "exposes cohort divergence vs the KITE-trading variant)."
        ),
        "bars": BARS,
        "bar_ms": BAR_MS,
        "assets": {
            "KITE/USDT": _kite_series(),
            "ETH/USDT": _eth_series(),
            "BTC/USDT": _btc_series(),
        },
    }
    out_path = Path(__file__).parent / "phase2-multi-class.json"
    out_path.write_text(json.dumps(fixture, indent=2) + "\n")
    print(f"wrote {out_path} ({sum(len(v) for v in fixture['assets'].values())} ticks)")


if __name__ == "__main__":
    main()
