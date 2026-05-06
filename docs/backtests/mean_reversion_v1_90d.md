# Backtest — `mean_reversion_v1` reference strategy (90 days, synthetic)

Closes Phase 2 acceptance gate **"Backtest reports for each reference
strategy committed under `docs/backtests/<class>_90d.md`"**
(`TODO.md` line 301).

## Scope

Demonstrates that `MeanReversionStrategy` (in
`reference-strategies/mean_reversion_v1/src/mean_reversion_v1/strategy.py`)
runs cleanly through the SDK backtest engine and produces the
expected per-bar trade signature. As with the momentum report, the
numbers are a **plumbing-correctness** signal, not an alpha claim.
Synthetic random walks have no mean-reverting structure to exploit,
and the reference impl trades aggressively (≈ 650 round-trips per
90d at `n_sigma = 2.00`) — fee drag alone accounts for a meaningful
share of the negative return on zero-drift series.

## Strategy summary

- **Class:** `mean_reversion_v1` — 16-bar μ/σ z-score; long entry on
  N-sigma down, short entry on N-sigma up, exit on mean re-cross
  or stop-loss.
- **Asset universe:** USDC (base), WKITE, WETH.
- **Operator-tunable params:** `n_sigma_x100` (default 200 = 2.00σ),
  `max_slippage_bps` (default 50), `position_fraction` (default 0.5),
  `stop_loss_price_e18` (default 0 = disabled).
- **Hard caps:** `max_position_size_usd = 10_000`,
  `fee_rate_bps = 2_000`.
- **Circuit invariants enforced by `mean_reversion_v1.circom`:**
  in-circuit stddev (`Σ(16·p_i − Σp)²`), z-score ≥ N-sigma threshold,
  exit-reason XOR (`is_signal_flip` + `is_stop_loss = is_exit`),
  asset universe, slippage, block window ≤ 100.

## Run

```bash
helios backtest \
    --strategy reference-strategies/mean_reversion_v1/src/mean_reversion_v1/strategy.py \
    --period 90d \
    --seed <seed>
```

`--period 90d` resolves to 2160 bars at a 1-hour cadence.
Initial capital `$10,000`, fees default `2 bps` round-trip.

## Results across five seeds

Refreshed for WS4 (NAV-target sizing, position-flip realisation, YR
backtest driver — see `docs/phase3-plan.md` step 16).

| Seed | Final NAV | Total return | Sharpe (ann.) | Max DD | Trades | Win rate |
|---:|---:|---:|---:|---:|---:|---:|
| 17   | $4,342.52 | -56.57% | -32.50 | 56.57% | 556 | 27.7% |
| 42   | $4,544.33 | -54.56% | -29.12 | 54.56% | 590 | 36.9% |
| 101  | $4,319.73 | -56.80% | -31.28 | 56.82% | 524 | 29.4% |
| 314  | $4,175.06 | -58.25% | -33.24 | 58.25% | 548 | 30.8% |
| 7331 | $4,699.57 | -53.00% | -30.95 | 53.03% | 550 | 33.1% |
| **median** | **$4,342.52** | **-56.57%** | **-31.28** | **56.57%** | **550** | **30.8%** |

Across all five seeds the trade count clusters at **554 ± 33** with a
**~31% win rate**, confirming the z-score gate fires consistently and
exits on mean re-crosses as designed. The aggregate negative return
on zero-drift random walks is the expected outcome — see *what these
numbers do not signal* below.

WS4 changes versus the prior writeup: trade count dropped ~14% because
the position-flip path (PR 2/3) now realises P&L on a single fill
instead of leaving an avg-entry stuck between two opposing legs, and
the LONG/SHORT entries that previously stacked on top of each other
without realising are now closed first via `_close_if_flipping`. NAV
endpoints land lower because realisations land where they should
instead of being silently absorbed by netted quantities.

## Representative NAV path (seed 42, median)

```
█                                                           
█████                                                       
███████                                                     
████████████████                                            
████████████████████                                        
██████████████████████████████                              
███████████████████████████████████                         
████████████████████████████████████████                    
███████████████████████████████████████████                 
████████████████████████████████████████████████████        
────────────────────────────────────────────────────────────
```

Smooth, monotonic NAV decay — no cliffs, no spikes. The strategy
fires roughly twice per day, accumulates fee drag, and the
random-walk price series doesn't mean-revert often enough to offset
it.

## What this report does *not* signal

- **Live alpha.** Synthetic random walks have no exploitable mean
  reversion; operators evaluating this strategy for live capital
  must replay against a real price tape (e.g., a 90-day BTC/ETH/WKITE
  hourly history).
- **Strategy correctness.** Verified independently by the
  reference-strategy pytest suite (33 cases under
  `reference-strategies/mean_reversion_v1/tests/`).
- **Engine correctness.** The SDK SHORT cash-accounting bug
  documented in the previous version of this report has been fixed
  (cash is now correctly credited on short entry and debited on
  cover; new SHORT-path tests in
  `packages/strategy-sdk/tests/test_backtest.py`). NAV at flat-price
  short = `initial − fee` as expected.

## Where the strategy is actually verified

| Surface | Lives in | Asserts |
|---|---|---|
| Strategy logic (LONG/SHORT/EXIT signal generation) | `reference-strategies/mean_reversion_v1/tests/test_strategy.py` | Z-score crossings produce the spec'd intents at the spec'd directions. |
| Circuit parity (Python ↔ circomlibjs Poseidon) | `reference-strategies/mean_reversion_v1/tests/test_witness.py` | The Python witness builder reproduces `gen-fixture-mr.js` outputs bit-exact. |
| SDK backtest engine SHORT path | `packages/strategy-sdk/tests/test_backtest.py` | Flat-price short is cash-neutral (NAV = initial − fee); falling price profits, rising price loses, magnitudes match expected per-bar mark-to-market. |
| Reputation engine handling of mean-rev cohort | `services/reputation/tests/test_score_822.py` | Cohort-relative Sharpe normalises mean-rev strategies against their own class median/IQR (not against momentum). |
| Full e2e (proof + on-chain trade) | `scripts/e2e-scenario-phase2.sh`, PR2.B (`724c5c1`) | A live `mean_reversion_v1` proof generated via the prover service is accepted by `MeanReversionV1VerifierAdapter` on anvil-kite. |

## Known follow-ups (for the SDK, not the strategy)

- **Position flipping.** The SDK's `_apply_intent` doesn't auto-EXIT
  the existing position before opening one in the opposite
  direction; mean-rev's `position <= 0` / `position >= 0` gates allow
  flipping signals to stack without flattening first, accumulating
  open exposure across the run. Phase 3 SDK hardening should add an
  explicit "flip = exit + open" path.
- **Sizing on accumulated positions.** `position_fraction = 0.5` on
  `available_capital` re-sizes against cash that hasn't reflected
  unrealized P&L; a vol-target or NAV-based sizing helper would be
  a natural extension once flipping is fixed.
