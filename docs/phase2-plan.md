# Helios Phase 2 — Implementation Plan

**Phase goal (per `TODO.md` lines 208–256):** Three strategy classes with real Groth16 proofs (momentum already shipped Phase 1), full §8.2 reputation formula replacing the Phase 1 proxy, hardened oracle (Poseidon swap + on-chain anchor + yield oracle), and a public `helios-strategy-sdk` v0.1 with working CLI subcommands.

**Target chain:** Kite testnet only (mainnet promotion is Phase 6).

**Deliverable:** This plan is the working draft. On approval it will be copied to `docs/phase2-plan.md` (mirroring the Phase 1 convention at `docs/phase1-plan.md`).

---

## Context — why this phase, why now

Phase 1 landed a vertical slice: one user → Sentinel → momentum strategy → ZK-attested trade → simplified reputation → permissionless defund. The slice exists end-to-end on Kite testnet (deployer `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25`, deployed 2026-04-27). What that slice cannot demonstrate is **the marketplace mechanism itself**: with one strategy class and a 2-term reputation proxy, allocation decisions are nearly deterministic and there is no signal divergence between strategies.

Phase 2 turns the slice into a market by (a) widening to three strategy classes with cohort-relative reputation, so allocation decisions become information-rich, and (b) opening the Strategy SDK so external operators can register a strategy without modifying Helios code — the precondition for Phase 3's allocator marketplace.

Outcome at end of Phase 2: multiple strategies per class with non-zero capital, reputation scores visibly diverging on realized P&L and drawdown, and a fresh contributor able to publish a strategy from `pip install helios-strategy-sdk` + the operator guide alone.

---

## Workstream map

| WS | Name | Depends on | Parallelizable with |
|----|------|------------|---------------------|
| WS1.A | Oracle Poseidon migration + on-chain anchor | — | WS4, WS5 |
| WS1.B | `mean_reversion_v1` circuit | WS1.A | WS1.C |
| WS1.C | `yield_rotation_v1` circuit | WS1.A | WS1.B |
| WS2.A | Reputation engine §8.2 rewrite | WS3.A typehash bump | WS1.* |
| WS2.B | Reference strategies (mean-rev + yield-rot) | WS1.B/C, WS4.A | each other |
| WS3.A | Verifier adapters + ReputationAnchor v2 + Oracle anchors | WS1.B/C, WS2.A field set | — |
| WS3.B | DeployPhase2 script | WS3.A | — |
| WS4.A | Strategy SDK v0.1 (agent base, helpers, test-PyPI publish) | — | WS1.* |
| WS4.B | `helios` CLI subcommands | WS4.A, WS2.B | WS5 |
| WS5 | `/audit` page | WS2.A | WS4.B |
| WS6 | Phase 2 e2e + acceptance | all above | — |

**Critical path (serial):** WS1.A → WS1.B → WS3.A → WS3.B → WS6 ≈ 12.5 days.
**Wall-clock with one engineer:** ~15–17 days. **With two:** ~9–11 days.

---

## WS1.A — Oracle Poseidon migration + on-chain anchor (M, ~3 days)

**Why first.** Both new circuits consume the Poseidon oracle root as a public input. Momentum already uses Poseidon internally (`circuits/momentum_v1.circom:123-138`) so the swap is additive, not breaking. Landing the chain first means circuit witnesses match production oracle bytes from day one.

**Deliverables**
- `services/oracle/src/oracle/poseidon.py` — Python Poseidon (vendor `poseidon-py` or wrap circomlibjs via subprocess if vector parity fails).
- `services/oracle/src/oracle/state.py` — replace keccak `_chain_root` (lines 71–84) with Poseidon. Keep ring-buffer semantics.
- `services/oracle/src/oracle/yield_state.py` — new mirror keyed by `market_id`, Poseidon-chained APY snapshots.
- `services/oracle/src/oracle/sources/yield_aave_stub.py`, `yield_compound_stub.py` — scripted-mode yield feeders for Phase 2 (real integrations Phase 5).
- `services/oracle/src/oracle/anchor.py` — periodic task: `OraclePriceAnchor.commit(root, windowStart, windowEnd)` and `OracleYieldAnchor.commit(...)` every N blocks (default 50).
- `contracts/src/OraclePriceAnchor.sol`, `contracts/src/OracleYieldAnchor.sol` — append-only ring buffer of `(root, windowStart, windowEnd, signer)` with EIP-712-signed commits. Two contracts, not one — different signer rotation cadences likely (Phase 5 yield integrations) and circuit public-input schemas already split.

**Tests**
- `services/oracle/tests/test_poseidon_chain.py` — vector parity against `circuits/test/momentum_v1.test.js` Poseidon fixtures (zero, max, boundary).
- `contracts/test/OraclePriceAnchor.t.sol`, `OracleYieldAnchor.t.sol` — only authorized signer, monotonic window, root retrieval.
- Scenario mode supports scripted yield differentials per `Helios.md §10.4`.

**Acceptance maps to:** TODO "Price oracle Poseidon-root anchored on-chain via periodic commit" + "Yield oracle signs APY snapshots".

---

## WS1.B — `mean_reversion_v1` circuit (M, ~3 days)

**Deliverables**
- `circuits/mean_reversion_v1.circom` — fork `momentum_v1.circom`. Reuse Poseidon chain template. **Invert direction logic**: long on N-sigma DOWN, short on N-sigma UP. Compute stddev in-circuit over 16-bar window via sum-of-squares (Welford too expensive in constraint count).
- `circuits/test/mean_reversion_v1.test.js` — valid long on N-sigma down, valid short on N-sigma up, valid exit on mean re-cross, invalid (amount > cap), invalid (asset out of universe), invalid (threshold not exceeded), boundary at exactly N-sigma.
- `circuits/Makefile:24` — append `mean_reversion_v1` to `CIRCUITS`.
- `circuits/scripts/check_constraints.sh` — CI gate: fail if any circuit exceeds 90% of declared budget (mean_rev budget = 20k).

**Public-input layout matches momentum** (14 signals): `trade_hash, declared_class, strategy_vault, params_hash, allocator, asset_in_idx, asset_out_idx, amount_in, min_amount_out, trade_direction, nonce, block_window_start, block_window_end, oracle_root` — so `MeanReversionV1VerifierAdapter._PUBLIC_INPUT_COUNT = 14`.

**Acceptance:** TODO "≤20k constraints; unit tests pass; verifier deployed + registered".

---

## WS1.C — `yield_rotation_v1` circuit (M, ~3 days)

**Deliverables**
- `circuits/yield_rotation_v1.circom` — fundamentally different shape from directional classes; no `trade_direction`. Public signals: `trade_hash, declared_class, M_from, M_to, amount_rotating, yield_oracle_root, allocator, nonce, window` (9 signals → adapter `_PUBLIC_INPUT_COUNT = 9`). Private: APY snapshot data, bridging cost, signal_threshold.
- Allowlist enforcement: Merkle inclusion of `(M_from, M_to)` against `MarketAllowlistRoot` committed in `StrategyRegistry`. Scales to Phase 5 cross-chain; bitmap would need redeploy per market addition.
- `circuits/test/yield_rotation_v1.test.js` — valid rotation, rejected when APY differential below threshold, rejected when market not in universe, rejected on root mismatch.
- `circuits/Makefile` — append `yield_rotation_v1` (budget 15k).

**Acceptance:** TODO "≤15k constraints; both markets allowlisted; verifier deployed + registered".

---

## WS2.A — Reputation engine §8.2 rewrite (L, ~5 days)

**Decision (resolved).** Engine computes per-window Sharpe from raw `Trade` events. **Subgraph schema does NOT change** — preserves graph-cli 0.83.0 / graph-ts 0.31.0 / apiVersion 0.0.7 pin (memory: Goldsky rejects WASM 0xFC; previous bump bricked v0.1.0 sync at 0%). Anchor on-chain stores `int256 score` + `bytes32 componentsHash`; `/audit` page reads full breakdown from engine HTTP.

**Deliverables**
- `services/reputation/src/reputation/score.py` — full replacement of Phase 1 formula (lines 36–54). Implements:
  - `PerformanceScore = 0.5 × NormSharpe(7d) + 0.3 × NormSharpe(30d) + 0.2 × NormSharpe(90d)` with cohort-relative `(Sharpe - median_class) / IQR_class`.
  - `RiskScore = 1 - clip(MaxDD90d / 5000, 0, 1)`.
  - `ProofScore = ValidProofs / TotalProofAttempts`.
  - `StakeScore = log(1 + stake/1000) / log(1 + max_stake_in_class/1000)`.
  - `AgeScore = clip(sqrt(trades_attested / 1000), 0, 1)`.
  - Aggregate: `0.40·perf + 0.25·risk + 0.15·proof + 0.10·stake + 0.10·age`.
- `services/reputation/src/reputation/cohort.py` — per-class median/IQR computation. `min_cohort_size = 2` — fall back to neutral cohort scaling (Sharpe with median=0, IQR=1) below threshold.
- `services/reputation/src/reputation/windows.py` — 7d/30d/90d slicing.
- `services/reputation/src/reputation/goldsky.py` — extend to fetch raw `Trade` events for 90d window per strategy (not just rollups).
- `services/reputation/src/reputation/api.py` — new endpoint `GET /v1/audit/{actor}` returning all five components + cohort stats + windowed Sharpes + resulting `componentsHash`.
- `services/reputation/src/reputation/signer.py` — typehash v2: add `bytes32 componentsHash` field; domain version `"1" → "2"`. Coordinated change with `contracts/src/ReputationAnchor.sol:19`.

**Tests**
- `services/reputation/tests/test_score_822_examples.py` — replicates §8.2 worked examples bit-for-bit.
- Property tests: cohort with one strategy returns rank-neutral; weights sum to 1.0; score in [-1, 1].
- EIP-712 round-trip with Foundry against new `ReputationAnchor` v2 typehash.

**Sequencing.** Land WS2.A in **shadow mode** first (compute + serve `/audit`, do not anchor on chain) for one window after WS3.B deploys, then flip env flag `REPUTATION_TYPEHASH_VERSION=2` to anchor. Avoids reputation thrash during cohort cold-start.

**Acceptance:** TODO "Full §8.2 reputation formula" + "/audit page exposes inputs" + "Reputation scores visibly diverge".

---

## WS2.B — Reference strategies (M, ~4 days, both in parallel)

**Deliverables** — clone `reference-strategies/momentum_v1/` template:
- `reference-strategies/mean_reversion_v1/` — strategy.py implements §10.3 (signal = N-period return < neg threshold for long; > pos threshold for short; exit on signal flip OR stop-loss; sizing `min(size_per_trade, available_capital × 0.5)` capped by `max_position_size_usd`; lookback 10–20 bars).
- `reference-strategies/yield_rotation_v1/` — strategy.py implements §10.4 (scan allowlisted lending markets; identify M_from/M_to where APY differential > threshold net of bridging; exit on differential drop + hysteresis; Phase 2 = Kite-local markets only). Uses MockSwapRouter (Phase 1 pattern; Algebra not on Kite testnet).
- Both registered via `contracts/script/RegisterPhase2Strategies.s.sol` with real stake. **Two strategies per class minimum** so cohort median/IQR is well-defined.

**Sharing.** Both classes reuse Phase 1 `StrategyVault` UUPS impl unchanged — vault is class-agnostic; class is enforced by registry + verifier mapping.

**Tests:** pytest per strategy; CI runs `helios test-proof --trade <fixture>` for each class against deployed verifier.

**Acceptance:** TODO "Multiple strategies of each class registered with non-zero capital".

---

## WS3.A — Contracts: adapters, anchor, typehash (M, ~3 days)

**Deliverables**
- `contracts/src/verifiers/MeanReversionV1Verifier.sol` (snarkjs **0.7.6** generated — pin per memory `project_snarkjs_pin`; bumping requires regenerating ALL artifacts).
- `contracts/src/verifiers/MeanReversionV1VerifierAdapter.sol` (`_PUBLIC_INPUT_COUNT = 14`).
- `contracts/src/verifiers/YieldRotationV1Verifier.sol`, `YieldRotationV1VerifierAdapter.sol` (`_PUBLIC_INPUT_COUNT = 9`).
- `contracts/src/ReputationAnchor.sol` — typehash v2 with `bytes32 componentsHash`; domain separator version `"2"`. UUPS upgrade keeping Phase 1 proxy address (memory: deployments file is canonical; subgraph datasource untouched).
- `contracts/src/OraclePriceAnchor.sol`, `OracleYieldAnchor.sol` (from WS1.A).
- `contracts/src/StrategyRegistry.sol` — add `marketAllowlistRoot(class, root)` setter for yield rotation.

**Tests**
- `contracts/test/MeanReversionV1VerifierAdapter.t.sol`, `YieldRotationV1VerifierAdapter.t.sol` — proof-fixture round-trip against snarkjs-generated proofs.
- `contracts/test/ReputationAnchorV2.t.sol` — typehash regression + UUPS upgrade preserves existing scores.
- Aggregate `forge coverage` ≥85% gate (CI already enforces; current is 97.54%).

**Acceptance:** TODO "Verifier deployed + registered" for both classes.

---

## WS3.B — DeployPhase2 script (S, ~1.5 days)

**Deliverables**
- `contracts/script/DeployPhase2.s.sol`:
  - Deploy `MeanReversionV1Verifier` + `MeanReversionV1VerifierAdapter`.
  - Deploy `YieldRotationV1Verifier` + `YieldRotationV1VerifierAdapter`.
  - Call `TradeAttestationVerifier.setVerifier(CLASS_MR, ...)` and `setVerifier(CLASS_YR, ...)` — class map already mutable per Phase 1; replaces mocks at `DeployPhase1.s.sol:104-110`.
  - Deploy `OraclePriceAnchor`, `OracleYieldAnchor`.
  - UUPS-upgrade `ReputationAnchor` proxy to v2 impl.
  - `StrategyRegistry.setMarketAllowlistRoot(CLASS_YR, merkleRoot)`.
  - Append addresses to `contracts/deployments/kite-testnet.json`.

**Backwards compat.** UserVault/AllocatorVault/StrategyVault UUPS proxies stay — Phase 2 doesn't change vault logic. ReputationAnchor is the only upgrade. No mainnet impact.

**Acceptance:** Kite testnet has both new verifiers + anchors live; addresses in deployments JSON.

---

## WS4.A — Strategy SDK v0.1 (M, ~3 days)

**Deliverables**
- `packages/strategy-sdk/src/helios/agent.py` — formalize abstract base with `declared_class`, `asset_universe`, `max_position_size_usd`, `fee_rate_bps`, `on_bar(asset, snapshot) -> TradeIntent | None`, `size_trade(intent, available_capital) -> Decimal`, `should_exit(asset, snapshot, position) -> bool`.
- `packages/strategy-sdk/src/helios/nav.py` — NAV / drawdown / Sharpe helpers.
- `packages/strategy-sdk/src/helios/backtest.py` — synthetic-bar engine for `helios backtest` and `helios simulate`.
- `packages/strategy-sdk/pyproject.toml` — version 0.1.0.
- `.github/workflows/publish-sdk-testpypi.yml` — publish on tag `sdk-v*` to test-PyPI.

**Acceptance:** TODO "`pip install helios-strategy-sdk` works from a test-PyPI mirror".

---

## WS4.B — CLI subcommands (M, ~3 days)

**Deliverables** — replace stubs in `packages/helios-cli/src/helios_cli/strategy.py:12-63`:
- `helios backtest --strategy ./my.py --period 90d --capital 10000` — uses WS4.A backtest engine; writes report to `docs/backtests/<class>/<strategy>_90d.md`.
- `helios simulate --strategy ./my.py --minutes 60` — mocked-market loop, CI-usable.
- `helios deploy --strategy ./my.py --vps user@server` — Dockerfile template (`packages/helios-cli/templates/Dockerfile.strategy`) + ssh bootstrap.
- `helios stake top-up --strategy <id> --amount N` — calls `StrategyRegistry.topUpStake`.
- `helios test-proof --trade <spec>` — full proof cycle: build witness → POST prover service → verifier read-call against deployed adapter.
- `docs/operator-guide.md` — end-to-end how-to for shipping a strategy.

**Tests:** CI invokes each subcommand against simulated runtime + Anvil fork.

**Acceptance:** TODO "External contributor could publish a momentum strategy using only the SDK + public docs".

---

## WS5 — `/audit` page (S, ~2 days)

**Deliverables**
- `frontend/src/app/audit/[actor]/page.tsx` — fetches engine `/v1/audit/{actor}`; renders all five §8.2 components, cohort median/IQR per window, raw windowed Sharpes, resulting `componentsHash`.
- `frontend/src/components/audit/ComponentBreakdown.tsx` — per-component card.
- `frontend/src/components/audit/CohortDistribution.tsx` — sparkline showing strategy's position in cohort.

Tokens-only (CLAUDE.md Tailwind rule); `[PASSPORT-STUB]` comment tags preserved per memory `project_kite_passport_block`.

**Acceptance:** TODO "/audit page exposes the inputs for every strategy's current score".

---

## WS6 — Phase 2 e2e scenario + acceptance (M, ~2 days)

**`scripts/e2e-scenario-phase2.sh`:**
1. Boot Anvil + oracle in scripted scenario mode (yield differentials per §10.4 + price drawdown for mean-rev signal).
2. Run `DeployPhase2.s.sol`.
3. Register 6 strategies (2 momentum, 2 mean-rev, 2 yield-rot) via SDK CLI `helios deploy --vps localhost`.
4. Drive 200 bars across 90d compressed time; oracle anchors commit every 10 bars.
5. Each strategy emits trades; prover service signs proofs (3 classes registered); `TradeAttestationVerifier` accepts each.
6. Reputation engine runs over 90d; assert:
   - All 5 §8.2 components present per strategy.
   - Cohort median/IQR well-defined (≥2 strategies per class).
   - Reputation diverges across strategies (variance > epsilon).
   - Drawdown-heavy strategy ranks lower than steady performer.
7. Playwright snapshot of `/audit/<actor>` for one strategy from each class.
8. **External-contributor flow:** spin a fresh container, `pip install helios-strategy-sdk` from test-PyPI, `helios backtest <fixture>`, `helios test-proof <fixture>` — green.

CI gates this as Phase 2's end-to-end integration test (path-filtered like Phase 1).

---

## Cross-cutting concerns

- **EIP-712 typehash v2 coordinated change.** Single PR touching `services/reputation/src/reputation/signer.py:53-112` and `contracts/src/ReputationAnchor.sol:19`. Domain version `"1" → "2"`. Engine refuses to sign when `REPUTATION_TYPEHASH_VERSION=2` until contract upgrade is on-chain.
- **No subgraph schema bump in Phase 2.** Engine computes from raw `Trade` events; `/audit` reads engine HTTP. Honors `project_subgraph_goldsky_wasm` pin.
- **Constraint budgets.** PTAU 16 = 65k. Momentum ~13k, mean-rev target ~17k, yield-rot target ~12k. CI gate at 90% of declared budget.
- **snarkjs pin.** All new verifier generation uses exactly `snarkjs@0.7.6` (memory `project_snarkjs_pin`).
- **UUPS upgrade.** Only `ReputationAnchor` upgrades in Phase 2. Vault proxies, registries, verifier registry all unchanged.
- **Hybrid testnet.** All Phase 2 deploys go to Kite testnet; mainnet is Phase 6.

---

## Risk register (likelihood × impact)

1. **Poseidon impl mismatch oracle ↔ circuit (M×H).** Trigger: vendored Python Poseidon diverges from circomlibjs constants. Mitigation: WS1.A includes vector-parity test against existing momentum circuit fixtures before any new circuit lands. Fallback: shell-out to `node` running circomlibjs in oracle service (slower but bit-exact).
2. **Reputation cohort starvation (H×M).** Trigger: <2 strategies in a class makes median/IQR undefined. Mitigation: `min_cohort_size = 2` gate in `score.py`, fall back to neutral cohort scaling (median=0, IQR=1). Fallback: hold Phase 2 acceptance until WS2.B registers ≥2 strategies per class — already in plan.
3. **EIP-712 typehash drift (M×H).** Trigger: engine merged before contract or vice versa. Mitigation: single PR, integration test deploys contract + runs engine sign + contract verify. Fallback: domain version mismatch causes verify to revert (safe failure, no bad state).
4. **Constraint budget overrun on mean_reversion (M×M).** Trigger: in-circuit stddev pushes past 20k. Mitigation: CI gate at 90%; fall back to passing precomputed stddev as private input with range check. Fallback: PTAU 16 has 65k headroom — soft target only.
5. **Goldsky subgraph break on schema accident (L×H).** Trigger: someone adds a field thinking it's harmless. Mitigation: explicit "no schema change" rule in this plan + PR template checkbox. Fallback: per memory, redeploy `helios/v0.1.x` increment, verify sync to 100% before cutover.

---

## Critical files

- `/home/emark/helios/services/reputation/src/reputation/score.py` (replace Phase 1 formula)
- `/home/emark/helios/services/reputation/src/reputation/signer.py` (typehash v2)
- `/home/emark/helios/services/oracle/src/oracle/state.py` (Poseidon swap)
- `/home/emark/helios/circuits/mean_reversion_v1.circom` (new)
- `/home/emark/helios/circuits/yield_rotation_v1.circom` (new)
- `/home/emark/helios/circuits/Makefile` (append classes)
- `/home/emark/helios/contracts/src/ReputationAnchor.sol` (UUPS upgrade, v2 typehash)
- `/home/emark/helios/contracts/src/OraclePriceAnchor.sol` (new)
- `/home/emark/helios/contracts/src/OracleYieldAnchor.sol` (new)
- `/home/emark/helios/contracts/src/verifiers/MeanReversionV1VerifierAdapter.sol` (new)
- `/home/emark/helios/contracts/src/verifiers/YieldRotationV1VerifierAdapter.sol` (new)
- `/home/emark/helios/contracts/script/DeployPhase2.s.sol` (new)
- `/home/emark/helios/services/prover/src/index.js:36` (register two new classes)
- `/home/emark/helios/reference-strategies/mean_reversion_v1/` (new)
- `/home/emark/helios/reference-strategies/yield_rotation_v1/` (new)
- `/home/emark/helios/packages/strategy-sdk/src/helios/agent.py` (formalize for v0.1)
- `/home/emark/helios/packages/helios-cli/src/helios_cli/strategy.py:12-63` (replace stubs)
- `/home/emark/helios/frontend/src/app/audit/[actor]/page.tsx` (new)
- `/home/emark/helios/scripts/e2e-scenario-phase2.sh` (new)
- `/home/emark/helios/docs/operator-guide.md` (new)
- `/home/emark/helios/docs/phase2-plan.md` (this plan, on approval)

---

## Verification (how to confirm Phase 2 is done)

End-to-end on Kite testnet:
1. `cd /home/emark/helios && forge test -vv` — green, coverage ≥ 85%.
2. `cd circuits && make mean_reversion_v1 && make yield_rotation_v1 && make test` — green; constraint counts within budget.
3. `forge script script/DeployPhase2.s.sol --rpc-url $KITE_RPC_URL --broadcast` — deploy succeeds; addresses appended to `kite-testnet.json`.
4. `bash scripts/e2e-scenario-phase2.sh` — green, asserts all six conditions in WS6.
5. Manual check: open `/audit/<momentum-strategy-actor>` — five §8.2 components render with non-zero cohort stats.
6. Fresh container test: `docker run --rm python:3.11 bash -c "pip install -i https://test.pypi.org/simple/ helios-strategy-sdk && helios backtest --help"` — green.
7. TODO.md Phase 2 acceptance section — every checkbox checked.

## Effort summary

| WS | Size | Days |
|----|------|------|
| WS1.A oracle Poseidon + anchor | M | 3 |
| WS1.B mean_reversion circuit | M | 3 |
| WS1.C yield_rotation circuit | M | 3 |
| WS2.A reputation §8.2 | L | 5 |
| WS2.B reference strategies | M | 4 |
| WS3.A contracts/adapters/typehash | M | 3 |
| WS3.B DeployPhase2 | S | 1.5 |
| WS4.A SDK v0.1 + test-PyPI | M | 3 |
| WS4.B CLI subcommands | M | 3 |
| WS5 /audit page | S | 2 |
| WS6 e2e scenario | M | 2 |

Critical-path serial: ~12.5 days. Wall-clock with one engineer: 15–17 days; with two splitting WS1.B/C and WS4.A/B: 9–11 days.
