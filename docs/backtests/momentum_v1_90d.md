# Backtest — `momentum_v1` reference strategy (90 days, synthetic)

Closes Phase 2 acceptance gate **"Backtest reports for each reference
strategy committed under `docs/backtests/<class>_90d.md`"**
(`TODO.md` line 301).

## Scope

Demonstrates that `MomentumStrategy` (in
`reference-strategies/momentum_v1/src/momentum_v1/strategy.py`)
runs cleanly through the SDK backtest engine and produces the
expected per-bar trade signature. The numbers below are the
**plumbing-correctness** signal — they are not, and should not be
read as, an alpha claim. The synthetic random walk supplied by
`helios.backtest.synthesize_random_walk` is by construction
zero-drift (LCG + Box-Muller-lite), so any strategy whose edge
depends on persistent directional moves will be net negative once
fees enter. Real evaluation requires real-market price tapes;
operators bring their own data when they fork this strategy.

## Strategy summary

- **Class:** `momentum_v1` — N-period return crosses a threshold,
  long entry on positive momentum, exit on signal flip.
- **Asset universe:** USDC (base), WKITE, WETH.
- **Operator-tunable params:** `signal_threshold` (default 0.015),
  `lookback_bars` (default 10), `max_slippage_bps` (default 30),
  `position_fraction` (default 0.5).
- **Hard caps:** `max_position_size_usd = 10_000`,
  `fee_rate_bps = 2_000` (20% perf fee above HWM).
- **Circuit invariants enforced by `momentum_v1.circom`:** asset
  membership in universe, `amount_in ≤ max_position_size`, slippage
  bound, direction matches a threshold, block window ≤ 100.

## Run

```bash
helios backtest \
    --strategy reference-strategies/momentum_v1/src/momentum_v1/strategy.py \
    --period 90d \
    --seed <seed>
```

`--period 90d` resolves to **2160 bars at a 1-hour cadence**
(`packages/helios-cli/src/helios_cli/strategy.py::_PERIOD_TABLE`).
Initial capital `$10,000`, fees default `2 bps` round-trip.

## Results across five seeds

| Seed | Final NAV | Total return | Sharpe (ann.) | Max DD | Trades | Win rate |
|---:|---:|---:|---:|---:|---:|---:|
| 17   | $8,446.18 | -15.54% | -3.24 | 17.15% | 150 | 37.3% |
| 42   | $8,212.68 | -17.87% | -3.87 | 20.92% | 151 | 32.0% |
| 101  | $7,682.22 | -23.18% | -5.61 | 26.08% | 141 | 31.4% |
| 314  | $8,861.91 | -11.38% | -2.28 | 13.97% | 155 | 31.2% |
| 7331 | $7,827.19 | -21.73% | -4.92 | 25.46% | 167 | 27.7% |
| **median** | **$8,212.68** | **-17.87%** | **-3.87** | **20.92%** | **151** | **31.4%** |

Across all five seeds the trade count clusters at **150 ± 13** with a
**31% win rate**, confirming the signal logic fires consistently and
exits on flip-overs as designed. Negative aggregate return is the
expected fee-adjusted outcome on zero-drift series.

## Representative NAV path (seed 42, median)

```
          █                                                 
███  ███  ███                                               
███████████████                                             
████████████████                                            
█████████████████ █                                         
█████████████████████                                       
██████████████████████                                      
███████████████████████████               ██ ██             
█████████████████████████████             ████████ █  █  █  
███████████████████████████████ ██████   ███████████████████
────────────────────────────────────────────────────────────
```

## What this report does *not* cover

- **Real-market alpha.** The CLI uses synthetic prices. Operators
  evaluating `MomentumStrategy` for live capital must replay against
  a real price tape they trust.
- **Cohort-relative reputation.** The §8.2 reputation engine ranks
  this strategy against its cohort (other `momentum_v1` strategies);
  see `services/reputation/tests/test_score_822.py` for component
  parity tests and `docs/reputation-math.md` for the formula.
- **On-chain execution.** Trades here are simulated fills against the
  same synthetic prices. The full execution path (witness build →
  prover → `TradeAttestationVerifier.verify` → `executeWithProof`) is
  exercised by the WS6 e2e (`scripts/e2e-scenario-phase2.sh`).
