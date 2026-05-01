# Reputation math

Long-form companion to `Helios.md §8`. The full per-component derivation, cohort statistics, and stake-weighting tradeoff write-up land in Phase 6 (see `TODO.md` Phase 2 §WS7.D). This file currently scopes only what Phase 2 ships and references — anything past the headings below is a Phase 6 placeholder.

---

## Cold start (Phase 2 / WS7.B, `Helios.md §8.7`)

A fresh strategy has no proofs, no NAV history, and — when it's the first of a new class — no peer cohort. Without an explicit bootstrap path that's a deadlock: the meta-strategy filter (e.g., `Sharpe ≥ 1.5`, `stake > $5k`) excludes new strategies, so they never earn the track record that would raise their score. WS7.B unblocks this with three coordinated mechanisms.

### 1. Cohort-size fallback — `min_cohort_size = 3`

`services/reputation/src/reputation/cohort.py` computes per-class median + IQR over the live cohort's window-Sharpe distribution and feeds them to `NormalizedSharpe = (Sharpe − median) / IQR`. When the cohort has **fewer than 3** active strategies, the cohort context falls back to the raw-Sharpe identity `(Sharpe − 0) / 1 = Sharpe`. Two reasons:

- **Avoid degenerate stats.** A 1-strategy "cohort" has IQR = 0; a 2-strategy cohort uses range as a proxy and still produces wild swings in `NormalizedSharpe` because a single peer's bad day moves the median by 50%. Three peers is the smallest cohort where `median + range` carries usable signal.
- **Don't punish first-mover classes.** A new class (e.g., the day `mean_reversion_v1` shipped) shouldn't have all its strategies stuck at `perf = 0` because the cohort-relative formula has nothing to compare against. The raw-Sharpe fallback grades them on absolute performance until the cohort fills out.

WS2.A originally pinned `min_cohort_size = 2`; WS7.B bumped it to 3 (`MIN_COHORT_SIZE = 3` in `cohort.py`). The bump is invisible in the on-chain interface — it changes only how the engine derives `PerformanceScore`.

### 2. Stake-only score floor — `trades_attested == 0`

`services/reputation/src/reputation/score.py` short-circuits when a strategy has no attested trades:

```
ReputationScore = w_stake · StakeScore        if trades_attested == 0
                = full §8.2 formula            otherwise
```

with `w_stake = 0.10` and `StakeScore = log(1 + stake/1000) / log(1 + max_stake/1000)` (§8.2). Other components are zeroed in the floor branch — performance/risk/proof have no signal yet, age is already 0 in §8.2's curve.

Two invariants this preserves:

- **Monotonic-in-trades.** As proofs accumulate, the score never drops below the cold-start floor in expectation. Operators can plan against `w_stake · StakeScore` as the worst case for a freshly-registered strategy with capital committed.
- **Componentshash distinguishes epochs.** The on-chain anchor (`ReputationAnchorV2`) hashes the five sub-scores; a cold-start row and a same-stake row with a track record produce different `componentsHash` values, so the typehash records each epoch faithfully.

Tested by `services/reputation/tests/test_score_822.py::test_zero_trades_returns_stake_only_floor` and `test_score_monotonic_non_decrease_as_proofs_accumulate`.

### 3. Bootstrap pool in the reference allocator — `bootstrap_share_bps`

The reputation engine is class-relative; the allocator is where capital actually flows. Sentinel (`services/sentinel/src/sentinel/allocator.py`) splits each user's capital into two pools:

| Pool | Capital | Eligibility | Ranking |
|---|---|---|---|
| Main | `(1 − bootstrap_share_bps/10000)` of total | All candidates passing the user's class/fee filters | `Rep × Capacity × FeeFit × ClassFit` (`§8.3`) |
| Bootstrap | `bootstrap_share_bps` of total | `trades_attested < min_attested_trades` (still respecting class/fee/capacity) | Stake-weighted with a flat performance prior |

If no candidate is bootstrap-eligible, the bootstrap budget rolls back to the main pool — a fully-graduated cohort doesn't leave capital idle. After both pools compute targets, Sentinel merges them per strategy and re-caps at `max_per_strategy_bps` so a strategy that wins both pools can't exceed the user's stated risk envelope.

**Why stake-weighted with a flat performance prior?** Stake is the only legible signal a fresh strategy carries; reputation is ~0, NAV history is empty. Weighting bootstrap capital by stake gives operators a deterministic on-ramp tied to the only thing they can put on the line up front. This is the same tradeoff `§8.1` flags — stake-weighting is a *deliberate* choice for the cold-start path, not a hidden subsidy.

Defaults (`docs/phase2-plan.md §WS7.B`):

- `bootstrap_share_bps = 1000` (10% of capital)
- `min_attested_trades = 50` (graduation threshold)

Both are first-class meta-strategy fields, exposed under "Advanced" on `/onboard` (`DESIGN.md §5` density target preserved). Templates set per-template defaults: conservative 5%, balanced 10%, aggressive 15% with a softer 30-trade graduation gate.

**Allocator opt-out.** Allocators that don't want a bootstrap pool are valid market participants — they just compete for non-bootstrap capital. Sentinel's bootstrap behavior is not part of the chain protocol; it's a strategy that competes against Helix and any third-party allocator.

---

## Phase 6 placeholders

The sections below land in Phase 6 alongside the rest of this file:

- Cohort statistics (median + IQR derivation, why exclusive quartiles, edge cases)
- Per-component scoring with worked examples (the Helios.md §8.2 numerical block, expanded)
- Stake-weighting tradeoff (mirroring `Helios.md §8.1` principle 2 + the v2 stake-stripped sub-rank candidate from `§8.5`)
- Drawdown extraction from NAV snapshots (Phase 2 proxy → realized-trade-P&L migration path)
- Cross-chain reputation propagation (LayerZero v2 send/receive math, `§8.6`)
