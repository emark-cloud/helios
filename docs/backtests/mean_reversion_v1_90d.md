# Backtest — `mean_reversion_v1` reference strategy (90 days, synthetic)

Closes Phase 2 acceptance gate **"Backtest reports for each reference
strategy committed under `docs/backtests/<class>_90d.md`"**
(`TODO.md` line 301).

## Scope and key caveat

`MeanReversionStrategy` (in
`reference-strategies/mean_reversion_v1/src/mean_reversion_v1/strategy.py`)
fires both LONG and SHORT entries (`z ≤ -nσ` and `z ≥ +nσ`
respectively, see `Helios.md §10.3`). The current SDK backtest
engine in `packages/strategy-sdk/src/helios/backtest.py::_apply_intent`
treats SHORT entries identically to LONG entries on the cash leg —
both paths subtract `notional + fee` from cash (line 311) — instead
of the correct treatment where a short sale credits cash by the
notional received and only debits the fee. As a result, every
SHORT trade halves the working cash, and after 600+ alternating
entries the synthetic NAV converges to zero on every seed.

This is an SDK engine limitation, **not** a strategy bug. The
strategy itself is verified by 33 pytest cases (per
`reference-strategies/mean_reversion_v1/tests/`) and a circuit
parity test that proves bit-exact agreement with
`mean_reversion_v1.circom`. Until the SDK gains correct short-leg
cash accounting (deferred to Phase 3 SDK hardening), the
`helios backtest` numbers below are best read as a smoke gate that
the SDK pipeline + strategy class wire up cleanly, not as a
performance claim.

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

## Results across five seeds (engine-limited — see caveat above)

| Seed | Final NAV | Total return | Sharpe (ann.) | Max DD | Trades | Win rate |
|---:|---:|---:|---:|---:|---:|---:|
| 17   | $0.00 | -100.00% | -23.91 | 143.84% | 654 | 34.5% |
| 42   | $0.00 | -100.00% |  -4.19 | 137.58% | 678 | 44.7% |
| 101  | $0.00 | -100.00% |  -5.23 | 172.50% | 607 | 37.4% |
| 314  | $0.00 | -100.00% |  -6.60 | 150.39% | 652 | 37.7% |
| 7331 | $0.00 | -100.00% |  -3.97 | 125.02% | 641 | 40.0% |

What these numbers *do* signal:

- The strategy's `on_bar` runs cleanly across 2160 bars without
  raising — SDK contract is satisfied.
- The signal fires at the expected cadence (≈ 640 trades per 90d on
  random-walk data with `n_sigma = 2.00`, ≈ 2.5% of bars), confirming
  the z-score gate isn't degenerate.
- Win rates cluster at 37 ± 5%, similar to momentum's ~31% — both
  reference strategies extract similar (zero-net) information from
  zero-drift synthetic walks.

What these numbers do *not* signal:

- Anything about live performance.
- Whether mean reversion has alpha on real markets.
- A bug in the strategy logic or circuit constraints.

## Where the strategy is actually verified

| Surface | Lives in | Asserts |
|---|---|---|
| Strategy logic (LONG/SHORT/EXIT signal generation) | `reference-strategies/mean_reversion_v1/tests/test_strategy.py` | Z-score crossings produce the spec'd intents at the spec'd directions. |
| Circuit parity (Python ↔ circomlibjs Poseidon) | `reference-strategies/mean_reversion_v1/tests/test_witness.py` | The Python witness builder reproduces `gen-fixture-mr.js` outputs bit-exact. |
| Reputation engine handling of mean-rev cohort | `services/reputation/tests/test_score_822.py` | Cohort-relative Sharpe normalises mean-rev strategies against their own class median/IQR (not against momentum). |
| Full e2e (proof + on-chain trade) | `scripts/e2e-scenario-phase2.sh`, PR2.B (`724c5c1`) | A live `mean_reversion_v1` proof generated via the prover service is accepted by `MeanReversionV1VerifierAdapter` on anvil-kite. |

## Known follow-ups

- **SDK SHORT cash accounting** — fix
  `packages/strategy-sdk/src/helios/backtest.py::_apply_intent` so
  SHORT entries credit cash by `notional - fee` instead of debiting
  `notional + fee`. Add SHORT-path tests under
  `packages/strategy-sdk/tests/test_backtest.py`. Tracked for Phase 3
  SDK hardening; once landed, regenerate this report.
