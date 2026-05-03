# Backtest — `yield_rotation_v1` reference strategy (90 days, synthetic)

Closes Phase 2 acceptance gate **"Backtest reports for each reference
strategy committed under `docs/backtests/<class>_90d.md`"**
(`TODO.md` line 301).

## Why this report uses a stand-alone harness

Yield rotation operates on a different cadence than the directional
classes. `MomentumStrategy` and `MeanReversionStrategy` listen to
**price bars** via the SDK base hook `on_bar`; `YieldRotationStrategy`
overrides `on_bar` to a no-op (`strategy.py:64-69`) and exposes
`on_yield_tick(ticks: dict[market_id, YieldTick])` instead. The SDK's
`run_backtest` engine drives `on_bar` exclusively — no public hook
yet for yield-tick feeds — so `helios backtest --strategy …
yield_rotation_v1/strategy.py` would emit zero trades for any input.

This report instead drives the strategy directly through a
stand-alone harness. The harness is reproducible, lives in
`docs/backtests/_yield_rotation_v1_harness.py`, and its body is
embedded below for review. It synthesises 90 days of hourly APY
observations across four allowlisted markets and tallies rotation
behaviour.

## Strategy summary

- **Class:** `yield_rotation_v1` — Poseidon-Merkle-attested rotation
  between two allowlisted lending markets when the destination's APY
  exceeds the source's by `signal_threshold + bridging_cost` bps.
- **Asset universe:** N/A. YR doesn't hold spot assets; it holds
  positions in money-market vaults keyed by `market_id` (uint64).
- **Operator-tunable params:** `allowlisted_markets` (required),
  `signal_threshold_bps` (default 80), `bridging_cost_bps` (default 30),
  `position_fraction` (default 0.5).
- **Hard caps:** `max_position_size_usd = 25_000`,
  `fee_rate_bps = 1_500` (15% perf fee — tighter than directional
  classes, which charge 2_000 bps).
- **Circuit invariants enforced by `yield_rotation_v1.circom`:**
  Poseidon-Merkle membership of `(m_from, apy_from)` and
  `(m_to, apy_to)` against `yield_oracle_root` (depth 6),
  Poseidon-Merkle membership of both `m_from` / `m_to` against the
  strategy's private allowlist root (depth 4) bound through
  `trade_hash`, `apy_to − apy_from ≥ signal_threshold + bridging_cost`,
  `m_from ≠ m_to`, `amount_rotating > 0`.

## Harness setup

- **Markets:** 4 allowlisted (`market_id ∈ {1, 2, 3, 4}`) with
  base APYs `{380, 420, 510, 290}` bps.
- **Tick cadence:** hourly → `90d × 24 = 2160` ticks.
- **APY trajectory per market:** `base + slow_drift + noise + jump`
  where `slow_drift` is a 14-day sinusoid, `noise ∈ [−15, +15]` bps,
  and `jump` fires on ~16% of ticks at ±50–100 bps.
- **Initial capital:** $50,000.
- **Strategy params:** `signal_threshold_bps = 80`,
  `bridging_cost_bps = 30` ⇒ rotation requires a ≥ 110 bps APY
  improvement net of bridging.

## Results across five seeds

| Seed | Rotations | Median diff (bps) | Positive-diff rotations | Avg active APY (bps) |
|---:|---:|---:|---:|---:|
| 17   |  9 | 139.0 |  9 / 9   | 510.9 |
| 42   | 12 | 123.5 | 12 / 12  | 509.3 |
| 101  |  6 | 124.5 |  6 / 6   | 509.6 |
| 314  |  7 | 121.0 |  7 / 7   | 511.4 |
| 7331 |  3 | 123.0 |  3 / 3   | 511.5 |
| **median** | **7** | **123.5** | **7 / 7** | **510.9** |

What these numbers signal:

- The strategy fires `RotationIntent`s only when the spread clears
  the `signal_threshold + bridging_cost` floor — every executed
  rotation has a positive APY differential ≥ 110 bps. Confirms the
  in-strategy gate (`differential < required → return None`,
  `strategy.py:108-109`) and matches the on-chain circuit constraint.
- Median rotation differential of **123 bps** is close to the floor;
  the strategy doesn't wait for huge spreads, it acts on the smallest
  incentive-compatible move. That matches the spec's intent (capture
  any net-positive yield improvement once bridging is paid).
- Average active APY converges to **~510 bps** across all seeds —
  the base APY of market 3, the highest-base in the allowlist.
  Confirms `max(candidates, key=apy)` selection (`strategy.py:88`)
  routes capital to the dominant market and stays there absent a
  spread-clearing alternative.
- Rotation cadence varies (3–12 over 90d) with seed entropy,
  showing the strategy isn't running a fixed schedule — it's truly
  signal-driven.

## What this report does *not* cover

- **Bridging time / multi-block confirmation.** The harness assumes
  instant rotation. The on-chain path (Phase 5 cross-chain LZ
  delivery) carries its own latency; per `Helios.md §10.4`, that's
  what `bridging_cost_bps` is meant to amortise.
- **Yield realised in dollars.** The harness reports APY-bps × time
  rather than realised cash because the SDK doesn't model yield
  accrual or compounding for YR yet. A full P&L model is Phase 3 SDK
  work; the on-chain deposit/withdraw P&L is observed directly via
  `NAVReported` in the e2e (`scripts/e2e-scenario-phase2.sh`).
- **Real-market alpha.** Synthetic APY traces; operators must
  re-run against real money-market data they trust.

## Where the strategy is actually verified

| Surface | Lives in | Asserts |
|---|---|---|
| Strategy logic (rotation gating, market selection) | `reference-strategies/yield_rotation_v1/tests/test_strategy.py` | `on_yield_tick` returns the expected `RotationIntent` exactly when the spec's threshold is met. |
| Circuit parity (Python ↔ circomlibjs Poseidon) | `reference-strategies/yield_rotation_v1/tests/test_merkle.py` | Yield-tree root + trade_hash bit-exact match `gen-fixture-yr.js`. |
| Reputation engine handling of YR cohort | `services/reputation/tests/test_score_822.py` | Cohort-relative Sharpe ranks YR strategies against their own class. |
| Full e2e (proof + on-chain rotation) | `scripts/e2e-scenario-phase2.sh`, PR2.C (`94848b3`) | A live `yield_rotation_v1` proof is accepted by `YieldRotationV1VerifierAdapter` on anvil-kite, with the canonical scenario crossing Compound-USDC > Aave-USDC at tick 5 (`TODO.md` line 248). |

## Reproducing the numbers

```bash
uv run --no-sync python docs/backtests/_yield_rotation_v1_harness.py
```

Full harness body lives in
[`docs/backtests/_yield_rotation_v1_harness.py`](_yield_rotation_v1_harness.py)
— the leading underscore keeps it out of any future doc-site index
without hiding it from contributors browsing the directory.

## Known follow-ups

- **SDK `on_yield_tick` engine support.** Add a YR-aware backtest
  driver to `packages/strategy-sdk/src/helios/backtest.py` so YR
  strategies surface in `helios backtest` like the directional
  classes. Tracked for Phase 3 SDK hardening.
- **Yield realisation model.** Track rotated capital + accrued
  yield in dollars rather than just bps × time, so the report can
  surface a Sharpe / max-DD comparable to the directional reports.
