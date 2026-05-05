# Helios Phase 3 — Implementation Plan

**Phase goal (per `TODO.md` lines 311–352).** Turn the marketplace mechanism into a real two-sided market: ship the public `helios-allocator-sdk` with a complete competitor surface, build **Helios Helix** as a second reference allocator entirely on top of that SDK, anchor allocator reputation alongside strategy reputation, and let a user pick between Sentinel and Helix on `/onboard` such that allocation decisions visibly diverge.

**Acceptance bar (verbatim from `TODO.md`).**
1. A user picks Sentinel at onboarding → flow works. Same user re-onboards picking Helix → flow works with different allocation decisions visible.
2. `helios-allocator init --name "TestThirdParty"` scaffolds a working allocator that can be registered on Kite testnet without any modifications to Helios code.
3. Allocator leaderboard on dashboard shows both Sentinel and Helix with diverging reputation as their decisions play out differently across users.

**Target chain.** Kite testnet only. Mainnet promotion is Phase 6 (`docs/deployment-strategy.md`).

**Passport posture.** Phase 3 does not touch onboarding — `[PASSPORT-STUB]` tags stay until Phase 4. The "user picks Sentinel vs. Helix" step is a frontend + Sentinel-and-Helix server change, not an AA-wallet change.

**Scope cuts already absorbed.** `Helios.md §11.4.1` (regime detection from BTC realized vol, correlation-aware greedy pick, regime-adaptive fee weighting) is post-hackathon Phase 1. Phase 3 ships **Helix-lite** per the `Helios.md §11.4` callout: continuous fee-fit factor over `score_weighted_allocation`, with regime fixed at NORMAL. The SDK still exposes the `detect_regime`, `pairwise_correlation_from_goldsky`, and `btc_realized_vol_30d` hooks so third-party allocators can adopt them earlier than Helix does.

---

## Workstream map

| WS | Name | Depends on | Parallelizable with |
|----|------|------------|---------------------|
| WS1.A | AllocatorSDK runtime — onboarding, drawdown, fees, tx submission | — | WS1.B, WS3 |
| WS1.B | AllocatorSDK helpers — regime, correlation, btc-vol | WS1.A types | WS1.A, WS3 |
| WS1.C | AllocatorSDK backtest harness | WS1.A | WS2, WS3 |
| WS2.A | `helios-allocator init` scaffold + template | WS1.A | WS2.B |
| WS2.B | `helios-allocator backtest \| simulate \| stake \| deploy \| logs` | WS1.A, WS1.C | WS2.A |
| WS2.C | `helios scaffold-strategy` + Strategy SDK README "Build with Claude Code" | WS2.A pattern | WS2.A, WS2.B |
| WS3.A | Helix service on top of AllocatorSDK (helix-lite math) | WS1.A, WS1.B | WS4 |
| WS3.B | DeployPhase3 + Helix on-chain registration | WS3.A, WS5.A | WS5 |
| WS4 | Strategy SDK hardening — YR backtest driver, position flipping, NAV sizing | — | any |
| WS5.A | Allocator reputation in the engine + signer | — | WS5.B |
| WS5.B | Subgraph: allocator entity, scores, rebalance ops | WS5.A schema | FE |
| WS6.A | Frontend `/allocators` directory + `/allocators/[name]` detail | WS5.B | FE-onboard |
| WS6.B | `/onboard` allocator-picker step | WS3.A health endpoint | WS6.A |
| WS6.C | Allocator leaderboard on `/dashboard` | WS5.B | WS6.A |
| WS7 | Phase 3 e2e + acceptance scenario (Sentinel vs Helix divergence) | all above | — |

**Critical path (serial):** WS1.A → WS3.A → WS5.A → WS5.B → WS6.A → WS7 ≈ 11–12 days.
**Wall-clock with one engineer:** ~17–19 days. **With two:** ~10–11 days.

---

## WS1.A — AllocatorSDK runtime (M, ~3 days)

**Why first.** Helix is built on this SDK as a third-party allocator would be (`Helios.md §11.4` last paragraph: "validates the AllocatorSDK from a fresh perspective"). Anything Helix needs that the SDK can't provide is a quality bug. Starting with the runtime forces the API surface decisions before two consumers (Helix + scaffold) lock in expectations.

**Deliverables**
- `packages/allocator-sdk/src/helios_allocator/runtime/__init__.py` — public `AllocatorRuntime` class. Composes the pieces below into one thing a `BaseAllocator` subclass plugs into.
- `packages/allocator-sdk/src/helios_allocator/runtime/onboarding.py` — read meta-strategy from `UserVault`, validate against the allocator's `supported_classes`, persist to local store. API mirrors `services/sentinel/src/sentinel/state.py::SentinelStore.upsert_user` so the cutover is mechanical.
- `packages/allocator-sdk/src/helios_allocator/runtime/drawdown.py` — 60s NAV polling task, drawdown evaluation per allocation, defund trigger. Hook signature: `async def on_drawdown_breach(user, alloc) -> None`.
- `packages/allocator-sdk/src/helios_allocator/runtime/fees.py` — opportunistic HWM-cross fee crystallization. Threshold configurable; default 5% per `services/sentinel/src/sentinel/loop.py::FEE_THRESHOLD_BPS`.
- `packages/allocator-sdk/src/helios_allocator/runtime/onchain.py` — extract `OnChainRunner` from `services/sentinel/src/sentinel/onchain.py` into the SDK. Sentinel's copy becomes a thin re-export. **Not a copy-paste**: rename to `AllocatorOnChain`, drop sentinel-specific `_log` keys, add `register_allocator(name, ranking_function_hash, supported_classes, fee_bps, stake_amount)` for first-time bootstrap. Web3 plumbing identical.
- `packages/allocator-sdk/src/helios_allocator/runtime/goldsky.py` — strategy directory query + reputation read. Lift from `services/sentinel/src/sentinel/goldsky.py`. Preserve the `StrategyDirectoryRow → StrategyCandidate` shape (sentinel already imports `_to_candidate` from there).
- `packages/allocator-sdk/src/helios_allocator/runtime/events.py` — WebSocket event emission. Sentinel's `SentinelEvent` becomes `AllocatorEvent` with the same fields plus a top-level `allocator_name`. Backwards-compatible alias `SentinelEvent = AllocatorEvent` so the existing `services/sentinel` code keeps importing the old name.
- `packages/allocator-sdk/src/helios_allocator/runtime/stake.py` — `top_up`, `withdraw_initiate`, `withdraw_finalize`, `slashed_amount` against `AllocatorRegistry`. The 7-day cooldown is contract-enforced (`Helios.md §6.6`); the SDK only surfaces it.
- `packages/allocator-sdk/src/helios_allocator/runtime/loop.py` — generalize `services/sentinel/src/sentinel/loop.py::SentinelLoop` to `AllocatorLoop`. Keep cadences (drawdown 60s, rank 300s, fees 300s) configurable. Sentinel's loop becomes a 30-line subclass that wires `SentinelAllocator` into the generic loop.

**Sentinel cutover (this WS, not a follow-up).** Sentinel must consume the SDK runtime in this PR — otherwise we ship a public SDK whose own first-party consumer doesn't use it, which is the inverse of the §11.4 quality signal we want. Acceptance: `services/sentinel/src/sentinel/loop.py` is < 50 lines and contains zero on-chain or Goldsky logic; `services/sentinel/src/sentinel/onchain.py` is removed. Existing sentinel tests pass unchanged.

**Tests**
- `packages/allocator-sdk/tests/test_runtime_drawdown.py` — synthetic NAV trace crossing the user's drawdown threshold; assert exactly one `defund_async` per breach, idempotent on the second tick.
- `packages/allocator-sdk/tests/test_runtime_fees.py` — NAV climbs > HWM × 1.05; assert single `settle_fee_async` call per cross.
- `packages/allocator-sdk/tests/test_runtime_loop.py` — replays the existing `services/sentinel/tests/test_loop.py::test_full_tick` against `AllocatorLoop` with `SentinelAllocator` injected. Identical assertions.
- `services/sentinel/tests/test_loop.py` — keep the file, retarget imports to the new path. Must pass without mock changes.

**Acceptance maps to:** TODO bullet "SDK handles: onboarding, drawdown monitoring at 60s, fee crystallization, defund/rebalance tx submission via Passport sessions, Goldsky integration, ReputationAnchor integration for allocator reputation, WS event emission, stake management, Docker packaging, local backtest."

---

## WS1.B — AllocatorSDK helpers (S, ~1.5 days)

**Why parallel with WS1.A.** Pure functions, no runtime hooks. Helix-lite only consumes `helix_fee_factor` directly; Helix-v2 (post-hackathon) and any third-party allocator that wants to outpace Helix can opt into the rest. Shipping all three now is the SDK quality story.

**Deliverables**
- `packages/allocator-sdk/src/helios_allocator/helpers/regime.py`
  - `Regime` enum (already in `types.py` — leave it there, re-export).
  - `detect_regime(btc_realized_vol_30d, historical_percentiles) -> Regime` per `Helios.md §11.4.1 (a)`.
  - `helix_fee_factor(strategy_fee_bps, user_max_fee_bps, regime) -> float` per the same section.
- `packages/allocator-sdk/src/helios_allocator/helpers/correlation.py`
  - `pairwise_correlation_from_goldsky(strategy_a, strategy_b, *, window_days=30) -> float`. Pulls 30-day NAV time series via the SDK's Goldsky client; computes Pearson over log-returns, not raw NAV (raw NAV correlation is dominated by long-run drift).
  - `helix_greedy_pick(user, ranked, max_pairwise_correlation=0.7) -> list[StrategyCandidate]` per §11.4.1 (b). **Note** Helix-lite does not call this; ships unused but tested for third parties.
- `packages/allocator-sdk/src/helios_allocator/helpers/market_data.py`
  - `btc_realized_vol_30d(price_anchor) -> float`. Reads the on-chain `OraclePriceAnchor` Poseidon-committed snapshot chain (Phase 2 WS1.A), reconstructs the 30-day BTC return series, computes annualized realized vol.
  - `btc_vol_percentiles_1y(price_anchor) -> dict[str, float]` returning at minimum `{"p20": ..., "p80": ...}` for `detect_regime`. Caches per process to avoid hammering the oracle anchor every tick.
- `packages/allocator-sdk/src/helios_allocator/helpers/__init__.py` — aggregate exports.

**Tests**
- `packages/allocator-sdk/tests/test_helpers_regime.py` — fee-factor monotonicity in fee headroom, regime-piecewise behaviour at the p20/p80 boundaries.
- `packages/allocator-sdk/tests/test_helpers_correlation.py` — synthetic NAV traces with known correlation (perfect, zero, anti). Greedy pick test: rank order [A, B, C] with corr(A,B)=0.9, corr(A,C)=0.3 selects [A, C] not [A, B] at threshold 0.7.
- `packages/allocator-sdk/tests/test_helpers_market_data.py` — replay anchor fixtures from `services/oracle/tests/fixtures/`; vol calculation matches a 4-decimal pre-computed reference.

**Acceptance maps to:** TODO bullet "Helpers: `default_top_k_allocation`, `score_weighted_allocation`, `pairwise_correlation_from_goldsky`, `btc_realized_vol_30d`, `detect_regime`."

---

## WS1.C — AllocatorSDK backtest harness (S, ~2 days)

**Why this WS at all.** TODO requires `helios-allocator backtest`, and `Helios.md §11.3` lists "Local backtesting harness against historical strategy P&L." Without this, an allocator author has no way to compare ranking changes pre-deploy.

**Deliverables**
- `packages/allocator-sdk/src/helios_allocator/backtest/runner.py` — `run_backtest(allocator, strategies, capital, period) -> BacktestReport`. Replays Goldsky-sourced strategy NAV traces day-by-day; on each day, calls `allocator.rank_strategies` + `allocate`, applies the resulting capital weights to the next day's NAV deltas. Produces aggregate user net P&L, drawdown, allocator-fee-take.
- `packages/allocator-sdk/src/helios_allocator/backtest/report.py` — markdown + JSON renderer. Same shape as `docs/backtests/momentum_v1_90d.md` so `helios-allocator backtest --output docs/allocators/<name>_90d.md` produces a writeup that's directly committable.
- `packages/allocator-sdk/src/helios_allocator/backtest/data.py` — historical NAV pull from Goldsky with a local cache so a rerun against the same period doesn't re-query.

**Tests**
- `packages/allocator-sdk/tests/test_backtest_runner.py` — fixture set of three strategies with deterministic NAV traces; `SentinelAllocator` and `HelixAllocator` produce different P&L on the same input.

**Acceptance maps to:** TODO `helios-allocator backtest` and the SDK "Local backtest" bullet.

---

## WS2.A — `helios-allocator init` scaffold (S, ~1.5 days)

**Why.** TODO acceptance: `helios-allocator init --name "TestThirdParty"` scaffolds a working allocator that registers on Kite testnet with **zero** changes to Helios code. This is the AI-native entry path called out in the 2026-05-05 judging-criteria audit (criterion D).

**Deliverables**
- `packages/helios-cli/src/helios_cli/templates/allocator/` — scaffold tree:
  - `pyproject.toml.tmpl` (depends on `helios-allocator-sdk`, `pydantic`, `httpx` only — no workspace deps; mirrors `project_strategy_sdk_distribution.md` memory).
  - `src/{name_snake}/allocator.py.tmpl` — runnable subclass of `BaseAllocator` over momentum/mean-rev/yield-rot, wired to `AllocatorRuntime`.
  - `src/{name_snake}/__main__.py.tmpl` — `python -m {name_snake}` boots the loop against env vars.
  - `Dockerfile.tmpl` — produced via `helios-allocator deploy`.
  - `README.md.tmpl` — quickstart + a "Build with Claude Code" block (5-line scaffold prompt + pointer to `CLAUDE.md`).
  - `.env.example.tmpl` — every var needed (RPC, Goldsky endpoint, allocator EOA key, allocator vault address).
- `packages/helios-cli/src/helios_cli/allocator.py::init` — replace stub with real scaffolder. Slug rules: enforce `Helios *` namespace reservation client-side with a clear error; the on-chain check is the source of truth.
- `packages/allocator-sdk/README.md` — add "Build with Claude Code" section per the same TODO line. 5-line scaffold prompt + pointer to `CLAUDE.md`.

**Tests**
- `packages/helios-cli/tests/test_allocator_init.py` — scaffold a `TestThirdParty` allocator into a tmp dir, assert tree shape, run `pip install .` against it in a venv, assert `python -c "import test_third_party.allocator"` succeeds and `BaseAllocator` is subclassed.
- Integration: the same scaffold is the input to WS7 e2e step 1 — registers on Kite testnet on its own without modifications.

**Acceptance maps to:** TODO bullet "CLI: `helios-allocator init`" + "Build with Claude Code" README addition.

---

## WS2.B — Allocator CLI commands (S, ~1.5 days)

**Deliverables**
- `helios-allocator backtest` — wraps WS1.C. `--allocator path/to/module:ClassName --period 90d --capital 50000 --output docs/allocators/<name>_90d.md`. Full report on disk, summary table to stdout via `rich`.
- `helios-allocator simulate --users 100` — run N synthetic meta-strategies (sample from realistic ranges), feed through the allocator, dump aggregate stats. Useful for tuning fee/correlation thresholds against typical user populations.
- `helios-allocator stake top-up | initiate-withdrawal | withdraw | balance` — `AllocatorRegistry` interactions via `AllocatorOnChain.stake.*`. `initiate-withdrawal` records the 7-day timer; `withdraw` errors clearly if cooldown not elapsed.
- `helios-allocator deploy --vps user@server` — copies template `Dockerfile`, builds image, scp + `docker run`. Reuses the strategy-deploy plumbing (`packages/helios-cli/src/helios_cli/templates/Dockerfile.strategy` is the model; allocator template is its sibling).
- `helios-allocator logs` — tails the allocator's `structlog` JSON via a local file or SSH. Single-process; no log aggregation.

**Tests** — pytest CLI smoke tests using `typer.testing.CliRunner` for each subcommand on a stubbed runtime. Live tests via the Phase 3 e2e (WS7).

**Acceptance maps to:** TODO bullet "CLI: `helios-allocator init | backtest | simulate | stake | deploy | logs`."

---

## WS2.C — `helios scaffold-strategy` + Strategy SDK readme (S, ~1 day)

**Why pulled into Phase 3.** TODO line 339–340 (added 2026-05-05 from the judging-criteria audit). Both SDKs need symmetric scaffolds for criterion D novelty. Doing it now amortizes the templating system already built for WS2.A.

**Deliverables**
- `packages/helios-cli/src/helios_cli/templates/strategy/<class>/` — one subdir per class (`momentum_v1`, `mean_reversion_v1`, `yield_rotation_v1`). Each emits a runnable subclass of `MomentumStrategy` / `MeanReversionStrategy` / `YieldRotationStrategy` plus `pyproject.toml`, README, `.env.example`, and a "next steps for Claude Code" comment block referencing `CLAUDE.md`.
- `packages/helios-cli/src/helios_cli/strategy.py::scaffold` — `helios scaffold-strategy <class> --name "MyMomentum" --target-dir ./mom`.
- `packages/strategy-sdk/README.md` — "Build with Claude Code" section, 5-line scaffold prompt, pointer to `CLAUDE.md`.

**Tests** — same pattern as WS2.A: scaffold, install, import.

**Acceptance maps to:** TODO bullets "`helios scaffold-strategy <class>` CLI" + "Strategy SDK README Build with Claude Code section."

---

## WS3.A — Helios Helix service (M, ~2 days)

**Why before WS5/WS6.** The frontend allocator-picker (WS6.B) needs a real Helix endpoint at `:8002/v1/` to show fee + manifest. The reputation engine (WS5.A) needs a registered Helix on chain to score against. Helix existing as a real service unblocks both.

**Deliverables**
- `services/helix/src/helix/allocator.py` — `HelixAllocator(BaseAllocator)`:
  - `name = "Helios Helix"`, `fee_rate_bps = 600`, supports the same three classes as Sentinel.
  - `rank_strategies` — base reputation × capacity × class-fit, multiplied by `helix_fee_factor` with `regime=NORMAL` (the v1 pinning per `Helios.md §11.4` callout). The regime hook is plumbed through `self.market_data` so v2 can flip it on without touching the rank function.
  - `allocate` — defers to SDK `score_weighted_allocation` over the top-K-by-rank set. Correlation-aware greedy is **not** wired in v1 (`§11.4.1 (b)` deferred); the helper exists in the SDK and Helix-v2 will call it.
- `services/helix/src/helix/service.py` — replace the current Phase 0 stub with a full FastAPI app composed via the WS1.A `AllocatorRuntime`. Endpoints mirror Sentinel's surface (`/v1/users/{user}/dashboard`, `/v1/users/{user}/timeline`, `/v1/users/{user}/events` WS, `/v1/strategies`).
- `services/helix/src/helix/__main__.py` — boot loop with cadence config from env (`HELIX_DRAWDOWN_INTERVAL_SEC`, etc.).
- `deploy/ecosystem.config.cjs` — add `helix` PM2 entry alongside `sentinel`. Same VPS, different port (`HELIX_PORT=8002`, `SENTINEL_PORT=8001` already in use).

**Tests**
- `services/helix/tests/test_allocator.py` — given the same candidate list as `services/sentinel/tests/test_allocator.py`, assert Helix produces a *different* allocation. The whole point is divergence; if Helix and Sentinel produce identical output on the same fixture, Helix is failing its differentiator and the test fails loud.
- `services/helix/tests/test_service.py` — health, dashboard, WS event ordering. Same shape as Sentinel's service tests.

**Acceptance maps to:** TODO bullets "`services/helix/` built entirely on top of allocator-sdk", "`helix_fee_factor` — fixed-weight fee penalty", "`helix_greedy_pick` — top-K greedy selection", "Runs alongside Sentinel on the VPS."

---

## WS3.B — DeployPhase3 + Helix on-chain registration (S, ~1 day)

**Deliverables**
- `contracts/script/DeployPhase3.s.sol`:
  - Loads existing Phase 2 addresses from `contracts/deployments/kite-testnet.json`.
  - Reserves the name `"Helios Helix"` via `AllocatorRegistry.reserveName` (multi-sig owner).
  - Deploys a second `AllocatorVault` proxy for Helix.
  - `registerAllocator("Helios Helix-shadow", helixVault, keccak256("helix_v1_ranking"), [MOM, MR, YR], 600, ALLOCATOR_STAKE)` — name suffixed `-shadow` for the same reason Sentinel's is in Phase 1; the multi-sig flips to the reserved name + sets `isReferenceBrand=true` via `assignReferenceBrand` in a follow-up tx so testnet ops can rotate keys without touching the brand.
  - Writes the new addresses to `contracts/deployments/kite-testnet.json` under `helix.{allocatorVault, allocatorId}`.
- `contracts/test/AllocatorRegistry.t.sol` — extend with: registering under a non-reserved name succeeds, registering with `"Helios Helix"` (reserved) reverts, `assignReferenceBrand` sets the flag.

**Tests** — extension to the existing AllocatorRegistry test suite. Foundry only.

**Acceptance maps to:** TODO bullet "Registered on `AllocatorRegistry` with `isReferenceBrand = true`, name `\"Helios Helix\"`, fee rate 600 bps."

---

## WS4 — Strategy SDK hardening carryover (M, ~3 days)

**Why in Phase 3.** Carried over from Phase 2 backtest writeups (TODO line 334). Without these, `helios backtest` against `YieldRotationStrategy` emits zero trades, and reference-strategy long runs over-leverage. None of these is allocator work, but a Phase 3 demo where Sentinel and Helix show identical allocations because YR strategies have no usable backtest signal is a worse demo. Doing it now also keeps Phase 4 (frontend) free of Python work.

**Deliverables**
- `packages/strategy-sdk/src/helios/backtest/runner.py` — add `on_yield_tick` driver path. Drives `MarketYieldTick` events from a fixture stream so `YieldRotationStrategy.on_yield_tick` fires. `on_bar` driver stays for directional classes.
- Remove `docs/backtests/_yield_rotation_v1_harness.py` once `helios backtest --strategy yield_rotation_v1` produces equivalent output.
- `packages/strategy-sdk/src/helios/agent/_apply_intent.py` — flip = exit + open. When mean-rev signal flips direction on an open position, emit an `EXIT` intent for the current side before the new `OPEN`. Tests for LONG→SHORT and SHORT→LONG transitions.
- `packages/strategy-sdk/src/helios/sizing.py` — NAV-based sizing helper. Re-sizes against current NAV (not stale cash) so reference strategies stop over-leveraging on long runs. Reference strategies opt in via `size_trade(nav_target=True)`.
- `docs/backtests/mean_reversion_v1_90d.md` and `momentum_v1_90d.md` — re-run after fixes, refresh tables.

**Tests** — `packages/strategy-sdk/tests/test_backtest_yr_driver.py`, `test_apply_intent_flip.py`, `test_nav_sizing.py`.

**Acceptance maps to:** TODO bullets "YR-aware backtest engine", "Position flipping in `_apply_intent`", "NAV-based / vol-target sizing helper".

**Deferred to a future PR (do not block Phase 3).** Mirroring remaining packages to test-PyPI (TODO line 338) blocks on test.pypi.org's web-UI availability for OIDC trusted-publisher registration; we already have the GitHub Releases fallback live. Track in `project_testpypi_oidc_setup.md` memory; flip when test-PyPI registration unblocks.

---

## WS5.A — Allocator reputation in the engine (M, ~2 days)

**Why.** TODO bullet "Reputation Engine computes allocator scores from aggregate user net P&L above HWM, drawdown discipline, user retention, stake." Without this, the allocator leaderboard (WS6.C, WS7 acceptance) has nothing to render.

**Deliverables**
- `services/reputation/src/reputation/engine.py` — branch on `ActorType`. New `_score_allocator` flow:
  - **Aggregate user net P&L above HWM** (dominant factor): sum across all delegations to this allocator the realized P&L net of fees above each user's HWM. Pulled from a new subgraph aggregation (WS5.B).
  - **Drawdown discipline**: ratio of "user-allocations whose drawdown breached threshold AND were defunded within 60s" to "user-allocations whose drawdown breached threshold". An allocator that lets a breach sit for 5 minutes loses score here.
  - **User retention**: 30-day rolling count of users who kept capital with this allocator vs. left. Inverted churn.
  - **Stake size**: same log curve as strategies (`Helios.md §8.2 StakeScore`).
  - Weights — first cut: 0.55 P&L / 0.20 drawdown / 0.15 retention / 0.10 stake. Documented in `docs/reputation-math.md` as v1; subject to revision based on the §8.2 weight-change discipline (any change is a v2 decision).
- `services/reputation/src/reputation/goldsky.py` — `_QUERY_ALLOCATOR_STATE` query: per allocator, aggregate user P&L, drawdown-breach response times, retention.
- `services/reputation/src/reputation/anchor.py` — already supports `ActorType.ALLOCATOR` per the signer (`signer.py:41`); confirm `postReputationUpdate` path is exercised. Add `actor_type` discriminator at the top of the engine tick.
- `docs/reputation-math.md` — append §"Allocator reputation v1" with the four-factor formula, weights, and rationale.

**Tests**
- `services/reputation/tests/test_engine_allocator.py` — synthetic ledger with two allocators. Allocator A: 3 users, all profitable, fast drawdown response. Allocator B: 3 users, mixed P&L, slow drawdown. Assert score(A) > score(B). Assert that an allocator with zero users gets a stake-only floor (cold-start parallel to §8.7).
- `services/reputation/tests/test_anchor_allocator.py` — `postReputationUpdate` round-trip with `actor_type=ALLOCATOR` lands the score on `AllocatorRegistry.currentReputation` via `ReputationAnchor`.

**Acceptance maps to:** TODO bullets "Reputation Engine computes allocator scores …" + "`postReputationUpdate` with `actor_type = ALLOCATOR`."

---

## WS5.B — Subgraph allocator entities (S, ~1.5 days)

**Why.** Allocator leaderboard, dashboard panels, and the engine's queries all read from Goldsky. The engine must not query the chain directly for aggregations.

**Deliverables**
- `subgraph/schema.graphql` — new entities:
  - `Allocator` — id (address), name, feeRateBps, stakeAmount, currentReputation, totalUsers, totalCapitalManaged, isReferenceBrand, registeredAt.
  - `AllocatorReputationUpdate` — id, allocator, score, lastUpdateBlock.
  - `AllocatorDecision` — id (txHash:logIndex), allocator, user, kind (`ALLOCATE | DEFUND | REBALANCE | SETTLE_FEE`), strategy, amountUsd, timestamp.
  - `UserDelegation` — id (user:allocator), user, allocator, capital, since.
- `subgraph/src/allocator.ts` — handlers for `AllocatorRegistry.AllocatorRegistered`, `AllocatorRegistry.ReputationUpdated`, `AllocatorRegistry.StakeChanged`, plus `AllocatorVault.AllocationCreated/Defunded/Rebalanced/FeeSettled`.
- `subgraph/src/user.ts` — augment existing user mapping to track `delegatedAllocator`.
- `subgraph/subgraph.yaml` — add `AllocatorRegistry` data source (Phase 1 deployment address pulled from `kite-testnet.json`); pin `apiVersion: 0.0.7` per the existing memory (`project_subgraph_goldsky_wasm.md`).

**Per existing memory (`project_subgraph_bigint_limitation.md`).** `Allocator.totalCapitalManaged` is per-event accumulation; consumers (reputation engine, FE leaderboard) must sum at query time. Document inline in the schema with a comment.

**Tests** — local `graph-cli build` + replay against an anvil dump; integration test in WS7.

**Acceptance maps to:** TODO bullet "Allocator leaderboards queryable via subgraph."

---

## WS6.A — `/allocators` directory + detail (M, ~2 days)

**Deliverables**
- `frontend/src/app/allocators/page.tsx` — directory grid:
  - Sentinel first card with "Official Reference" badge.
  - Helix second card with the same badge.
  - Space below for third-party allocators (queried from subgraph; pinned card shape).
  - Per card: name, fee rate, supported classes, ranking-function one-sentence + "view code" link (GitHub permalink), current users, total capital managed, reputation, stake.
- `frontend/src/app/allocators/[name]/page.tsx` — detail page:
  - Header: name, brand badge, operator address, registration date.
  - Reputation breakdown: P&L / drawdown / retention / stake with explainer copy referencing `docs/reputation-math.md`.
  - Recent decisions table from `AllocatorDecision` entity.
  - List of users currently delegated, with their P&L vs HWM.
  - "Code" tab linking to the allocator's GitHub source (Sentinel + Helix only for now; third parties opt in via a `homepage_url` on-chain manifest field — left as a Phase 5 follow-up).
- `frontend/src/lib/queries/allocators.ts` — Goldsky GraphQL queries. Sum `Allocator.totalCapitalManaged` across events at query time per the WS5.B memory note.

**Tests** — Playwright smoke: `/allocators` lists 2 cards, both branded; navigate to `/allocators/Helios%20Sentinel` shows reputation breakdown.

**Acceptance maps to:** TODO bullets "`/allocators` directory" + "`/allocators/[name]` detail page."

---

## WS6.B — `/onboard` allocator-picker step (S, ~1 day)

**Deliverables**
- `frontend/src/app/onboard/AllocatorPicker.tsx` — new step inserted between "review meta-strategy" and "sign". Two cards: Sentinel (default) and Helix. Each shows fee rate, ranking summary, current reputation, link to detail.
- `frontend/src/app/onboard/OnboardClient.tsx` — pass the chosen allocator address through to the `delegateToAllocator` call. Phase 1's stub flow only delegates to Sentinel; the new flow uses the chosen vault.
- Persist the choice in localStorage so re-onboarding remembers (until the AA wallet's user-prefs path lands in Phase 4).

**Tests** — Playwright: pick Sentinel, complete onboard, assert delegation goes to `sentinelAllocatorVault`. Re-run picking Helix; assert delegation goes to `helixAllocatorVault`.

**Acceptance maps to:** TODO bullet "`/onboard` adds an allocator-picker step."

---

## WS6.C — Allocator leaderboard on `/dashboard` (S, ~1 day)

**Deliverables**
- `frontend/src/app/dashboard/components/AllocatorLeaderboard.tsx` — small panel: top 5 allocators by reputation, with delta (24h), fee, total capital. Sentinel/Helix labelled.
- Wire into the existing dashboard layout. Place under the activity rail, above the strategy leaderboard (which exists today).

**Tests** — Playwright: leaderboard renders with 2 rows post-Phase-3-deploy; Sentinel and Helix scores diverge after the e2e replay.

**Acceptance maps to:** TODO Phase 3 acceptance bullet 3.

---

## WS7 — Phase 3 e2e + acceptance scenario (S, ~2 days)

**Why.** Replays the entire Phase 3 acceptance bar against a fresh stack so a regression in any layer fails the gate. Mirrors `scripts/e2e-scenario.sh` from Phase 1 and Phase 2.

**Deliverables**
- `scenarios/phase3-divergence.py` — boots Sentinel + Helix against the same anvil + Goldsky-against-anvil stack, drives 4 demo users:
  1. User A picks Sentinel. Capital flows.
  2. User B picks Helix. Capital flows. **Asserts the resulting allocation set is materially different from User A's** (≥ 1 strategy in one set is not in the other, OR weights differ by ≥ 5% on a shared strategy).
  3. Drawdown event on a strategy User A holds. Sentinel defunds within one tick.
  4. NAV climbs above HWM × 1.05 on a strategy User B holds. Helix settles fees.
- `scripts/e2e-phase3.sh` — wrapper that boots stack, runs the scenario, validates subgraph state, asserts both Sentinel and Helix have non-zero `currentReputation`.
- `packages/helios-cli/tests/test_third_party_init_acceptance.py` — runs `helios-allocator init --name "TestThirdParty"` into a tmp dir, installs it, registers it on the local anvil via the resulting `python -m test_third_party register` command, asserts it shows up in `AllocatorRegistry.allocatorList`. **No edits to Helios code allowed in this test.**

**CI wiring**
- `.github/workflows/phase3-e2e.yml` — runs `e2e-phase3.sh` on every PR touching `packages/allocator-sdk/**`, `services/sentinel/**`, `services/helix/**`, `services/reputation/**`, `frontend/src/app/{allocators,dashboard,onboard}/**`, or `subgraph/**`.

**Acceptance maps to:** TODO Phase 3 acceptance bullets 1, 2, 3 — collectively.

---

## Cross-cutting concerns

- **Sentinel must keep working at every commit.** WS1.A's cutover is the highest-risk merge — split into ≥ 3 PRs (extract, switch, delete). Run `services/sentinel/tests/` after each. Phase-2 e2e (`scripts/e2e-scenario.sh`) must stay green between PRs.
- **No new on-chain ABI changes.** Phase 3 uses the existing `AllocatorRegistry` shape from Phase 1. WS3.B is deploy + reservation only. If a contract change is discovered to be necessary, it crosses the WS3.A boundary and needs an explicit phase amendment (Phase 5 already redeploys for ReputationAnchorV2 cutover per `project_reputation_phase1_simplified.md` — bundle into that re-deploy if possible).
- **Memory `project_strategy_sdk_distribution.md` applies to the allocator SDK too.** No workspace runtime deps in `helios_allocator.*` — wheel must install from public PyPI. CI needs a `pip install helios-allocator-sdk --index-url https://test.pypi.org/simple/` smoke test to catch regressions.
- **Memory `project_subgraph_goldsky_wasm.md` still binding** — do not bump `graph-ts` / `graph-cli` versions when adding the allocator entities.
- **Phase 3 e2e runtime** — long. Estimate 8–10 min for `scenarios/phase3-divergence.py`. Use `run_in_background` + Monitor per `project_phase2_e2e_runtime.md` memory.

---

## Risk register (likelihood × impact)

| Risk | L × I | Mitigation |
|------|-------|------------|
| Sentinel cutover to SDK breaks Phase 2 e2e mid-stream | M × H | Multi-PR split; run `e2e-scenario.sh` between PRs; revert plan = swap in legacy `OnChainRunner` import. |
| Helix produces identical output to Sentinel on demo data | M × H | WS3.A test enforces divergence; if it fails, increase the fee penalty curvature OR seed the demo with strategies whose fees straddle a typical cap. |
| Allocator reputation P&L sum is dominated by one big user (loud minority) | M × M | Document in `reputation-math.md` as known v1 behavior; weight cap on per-user contribution is a v2 lever. |
| Subgraph aggregation slow / wrong on large user sets | M × M | Sum-at-query-time per existing memory; add per-allocator caches in the FE query layer if p95 > 800ms. |
| `helios-allocator init` scaffold drifts from real SDK API | L × H | WS7 acceptance test runs the scaffold and registers it on chain — any drift fails CI. |
| Frontend allocator-picker stuck on Sentinel because `delegateToAllocator` is hard-coded | L × M | Audit `OnboardClient.tsx` early; the `[PASSPORT-STUB]` flow probably hard-codes the address. Lift to a prop in WS6.B day 1. |

---

## Critical files (touched in Phase 3)

- `packages/allocator-sdk/src/helios_allocator/{base.py,types.py}` — surface stays stable; runtime/* and helpers/* are new.
- `services/sentinel/src/sentinel/loop.py`, `onchain.py`, `goldsky.py`, `state.py` — relocated into the SDK.
- `services/helix/src/helix/{allocator.py,service.py,__main__.py}` — fully implemented.
- `packages/helios-cli/src/helios_cli/{allocator.py,strategy.py,templates/}` — scaffold realization.
- `packages/strategy-sdk/src/helios/{backtest/runner.py,agent/_apply_intent.py,sizing.py}` — Phase 2 carryover.
- `services/reputation/src/reputation/{engine.py,goldsky.py,anchor.py}` — allocator branch.
- `subgraph/{schema.graphql,subgraph.yaml,src/allocator.ts,src/user.ts}` — new entities + handlers.
- `frontend/src/app/{allocators/page.tsx,allocators/[name]/page.tsx,onboard/AllocatorPicker.tsx,dashboard/components/AllocatorLeaderboard.tsx}` — new surfaces.
- `contracts/script/DeployPhase3.s.sol` — Helix on-chain registration.
- `scenarios/phase3-divergence.py`, `scripts/e2e-phase3.sh` — acceptance harness.

---

## Verification (how to confirm Phase 3 is done)

Run from a fresh checkout against Kite testnet:

```bash
forge test -vv                                                   # contracts unchanged + AllocatorRegistry tests pass
pnpm --filter subgraph build                                     # schema compiles, mappings type-check
pytest packages/allocator-sdk packages/helios-cli services/{sentinel,helix,reputation}
pnpm --filter frontend test:e2e -- onboard.spec allocators.spec  # Playwright signature flows
./scripts/e2e-phase3.sh                                          # full divergence scenario
helios-allocator init --name "TestThirdParty" -t /tmp/tp && \
  cd /tmp/tp && pip install -e . && python -m test_third_party register  # acceptance bullet 2
```

All pass → Phase 3 acceptance bar met. Move to Phase 4.

---

## Effort summary

| WS | Days | Critical-path? |
|----|------|----------------|
| WS1.A | 3.0 | yes |
| WS1.B | 1.5 | no |
| WS1.C | 2.0 | no |
| WS2.A | 1.5 | no |
| WS2.B | 1.5 | no |
| WS2.C | 1.0 | no |
| WS3.A | 2.0 | yes |
| WS3.B | 1.0 | no |
| WS4 | 3.0 | no |
| WS5.A | 2.0 | yes |
| WS5.B | 1.5 | yes |
| WS6.A | 2.0 | yes |
| WS6.B | 1.0 | no |
| WS6.C | 1.0 | no |
| WS7 | 2.0 | yes |
| **Total (one engineer, sequential)** | **26 days** | |
| **Wall-clock (one engineer with parallelism)** | **17–19 days** | |
| **Wall-clock (two engineers)** | **10–11 days** | |

---

## Execution order (Claude Code workflow)

The constraint when driving this with Claude Code is **PR review attention**, not engineer-days. Steps are ordered to keep PRs small, ship a Sentinel-vs-Helix demo by step 11, and defer SDK-author and Phase-2-carryover work until the demo path is wired. Each row = one Claude Code session = one PR.

**Status legend:** `[ ]` not started · `[~]` in progress · `[x]` merged · `[!]` blocked

| # | Status | Step | Gate before merge |
|---|--------|------|-------------------|
| 1 | `[~]` | **WS1.A PR 1/3 — extract** runtime/onchain/goldsky/loop into `helios_allocator.runtime.*` as new modules. Sentinel keeps importing from old paths. | Sentinel tests + Phase 2 e2e green. |
| 2 | `[ ]` | **WS1.A PR 2/3 — switch** Sentinel to import from the SDK runtime. Old `services/sentinel/{loop,onchain,goldsky,state}.py` become thin re-exports. | `scripts/e2e-scenario.sh` green. |
| 3 | `[ ]` | **WS1.A PR 3/3 — delete** re-export shims. Sentinel ≤ 50 lines of glue. | Sentinel tests + Phase 2 e2e green. |
| 4 | `[ ]` | **WS1.B — SDK helpers** (`detect_regime`, `helix_fee_factor`, correlation, BTC vol). | `pytest packages/allocator-sdk` green. |
| 5 | `[ ]` | **WS5.A — Allocator reputation engine branch** + `docs/reputation-math.md` §"Allocator reputation v1". | `pytest services/reputation` green. |
| 6 | `[ ]` | **WS5.B — Subgraph allocator entities** + handlers. | `pnpm --filter subgraph build` green. |
| 7 | `[ ]` | **WS3.A — Helix service** (allocator + service + `__main__` + PM2 entry). Divergence assertion is the gate. | `pytest services/helix` green; divergence-vs-Sentinel test passes. |
| 8 | `[ ]` | **WS3.B — `DeployPhase3.s.sol`** + `AllocatorRegistry.t.sol` extension + write addresses to `kite-testnet.json`. | `forge test -vv` green. |
| 9 | `[ ]` | **WS6.A — `/allocators` directory + detail.** | Playwright `allocators.spec` green. |
| 10 | `[ ]` | **WS6.B — `/onboard` allocator-picker** + `OnboardClient.tsx` plumbing. | Playwright `onboard.spec` green; localStorage choice round-trips. |
| 11 | `[ ]` | **WS6.C — Dashboard allocator leaderboard.** | Playwright dashboard spec green; Sentinel + Helix both render. |
| 12 | `[ ]` | **WS2.A — `helios-allocator init` scaffold + template + SDK README "Build with Claude Code".** | `pytest packages/helios-cli/tests/test_allocator_init.py` green. |
| 13 | `[ ]` | **WS1.C — Backtest harness** in the SDK. | `pytest packages/allocator-sdk/tests/test_backtest_runner.py` green. |
| 14 | `[ ]` | **WS2.B — `helios-allocator {backtest, simulate, stake, deploy, logs}`.** | Typer CliRunner smoke tests green. |
| 15 | `[ ]` | **WS2.C — `helios scaffold-strategy` + Strategy SDK README.** | Scaffold-install-import test green for all three classes. |
| 16 | `[ ]` | **WS4 — Strategy SDK hardening** (YR backtest driver / position flipping / NAV sizing) split as 3 small PRs. | `pytest packages/strategy-sdk` green; refreshed backtest writeups committed. |
| 17 | `[ ]` | **WS7 — `scenarios/phase3-divergence.py` + `scripts/e2e-phase3.sh` + GH Action.** | Full divergence scenario green; third-party-init acceptance test green with zero Helios edits. |

### Parallelism via background sub-agents

While reviewing each step's PR, useful background `Agent` work that does **not** compete for the review queue:

- **During steps 1–3 (WS1.A chain)** → draft step 4 (WS1.B helpers + tests) and the three step-16 (WS4) small fixes. They land in the gaps between later steps.
- **During step 5 (WS5.A)** → draft step 6 subgraph schema so it's ready to commit immediately after.
- **During step 9 (WS6.A)** → draft steps 10 and 11; all three share the same Goldsky query layer.
- **Do not background-draft step 7 (WS3.A).** Helix is the load-bearing differentiator and deserves a focused session.

### Hard rules per step

1. Every PR runs `forge test` + relevant `pytest` suite + `scripts/e2e-scenario.sh` (Phase 2 e2e) before merge. **WS1.A is the only step where the Phase 2 e2e is at real risk** — do not skip it there.
2. No step touches contract ABIs beyond WS3.B. A contract change discovered mid-stream is a phase amendment, not a quiet edit.
3. Update this table's status column in the same PR that lands the step. The doc is the source of truth for Phase 3 progress.
