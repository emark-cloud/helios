# Phase 1 — detailed execution plan

Companion to `TODO.md` Phase 1 section and `Helios.md §6 / §9 / §11`. Read after both. Updated 2026-04-25.

## Phase 1 in one sentence

End-to-end vertical slice on Kite testnet: user signs a meta-strategy (EOA-stubbed for Passport) → Sentinel routes capital to a momentum strategy → strategy executes a real Groth16-attested trade → Reputation Engine posts an update → scenario mode drives a drawdown → permissionless `defundStrategy` fires → replacement allocation lands → dashboard reflects every step.

## Working assumptions

1. **Passport is blocked externally** (see `docs/kite-passport-notes.md`). Every Passport touchpoint stubs to EOA + EIP-712 signatures, marked `[PASSPORT-STUB]` in code with a pointer to the swap-in checklist.
2. **Hackathon deadline extended ≥2 weeks.** Use the room to hit 85% coverage and a clean e2e — don't ship Phase 1 with corners cut.
3. **VPS not yet live.** Local-first development on docker-compose; benchmarks move to Servarica box once provisioned.
4. **Goldsky + Vercel done.** Subgraph deploy and frontend preview pipelines work end-to-end.

## Workstream layout

Five parallel workstreams. WS1 (contracts) and WS2.A (momentum circuit) are independent long poles — start both immediately. WS2.B–D and WS4 fan out as soon as their dependencies land.

```
       ┌──────── WS1 contracts ────────┐
                                       ├─→ WS2.B services ──┐
       ┌──── WS2.A momentum circuit ───┘                    ├─→ WS2.C Sentinel ──┐
       │                                                    │                    │
       └──→ deploy verifier                                  └─→ WS2.D strategy ─┤
                                                                                 ├─→ WS3 scenario+e2e ─→ WS5 acceptance
                                       WS4 frontend (parallel) ──────────────────┘
```

---

## WS1 — Contracts (long pole, est. 7–9 days)

Branch: `phase-1-contracts`. Implementation order matters because of struct sharing and deploy ordering.

### Implementation order

| # | Contract | Why this order |
|---|---|---|
| 1 | `StrategyRegistry.sol` | Simplest — stake mgmt + reputation slot. No external deps. |
| 2 | `AllocatorRegistry.sol` | Mirrors StrategyRegistry pattern; adds reserved-name + `isReferenceBrand` flag. |
| 3 | `ReputationAnchor.sol` | Signer-gated `postReputationUpdate`; OApp gate for `postCrossChainUpdate` is a no-op stub for Phase 1. Reads from both registries. |
| 4 | `TradeAttestationVerifier.sol` | `verifiersByClass` registry; `verify(class, proof, publicInputs)` dispatches. |
| 5 | `StrategyVault.sol` (UUPS) | `executeWithProof`, `reportNAV`, `distributeRealized`, `withdrawToAllocator`, `slash`. Calls TradeAttestationVerifier then router. |
| 6 | `AllocatorVault.sol` (UUPS) | `allocateToStrategy`, `defundStrategy` (permissionless when DD breached), `rebalance`, `settleStrategyFee`, `withdrawAllocatorFees`. |
| 7 | `UserVault.sol` (UUPS) | `setMetaStrategy` (EOA sig stub `[PASSPORT-STUB]`), `deposit`, `delegateToAllocator(sessionTTL)`, `withdraw`, `settleAllocatorFee`. |

### Test surface (per contract)

Tests live alongside in `contracts/test/<Contract>.t.sol`. Coverage gate: ≥ 85% branch via `forge coverage --report summary`.

- **UserVault**: out-of-bounds delegation (`sessionTTL > meta.maxSessionTTL` → revert), reentrancy guard on `withdraw`, `[PASSPORT-STUB]` EIP-712 sig validation
- **AllocatorVault**: drawdown-breach permissionless defund (random EOA can call), rebalance preserves total notional, fee settlement matches HWM math
- **StrategyVault**: invalid proof → revert, unregistered class → revert, slash decrements stake correctly, NAV monotonicity within a snapshot
- **StrategyRegistry**: 7-day stake cooldown enforcement, slash math, deactivation gates further allocations
- **AllocatorRegistry**: reserved-name attempt by non-deployer → revert, `isReferenceBrand` flag is signer-only
- **ReputationAnchor**: signer rotation, replay protection on `postCrossChainUpdate` stub, only registered signers can post
- **TradeAttestationVerifier**: dispatch correctness, unknown class → revert, verifier swap (per-class redeploy)

### Deploy

`contracts/script/DeployPhase1.s.sol`:

1. Deploy registries (Strategy, Allocator).
2. Deploy `ReputationAnchor`; register reputation signer + oracle signer.
3. Deploy `TradeAttestationVerifier` (verifiers registered later).
4. Deploy implementation + proxy for each vault.
5. Wire registry → anchor cross-references.
6. Write addresses to `contracts/deployments/kite-testnet.json` (auto-loaded by `packages/contracts-abi-py/addresses.py` and `packages/contracts-abi/src/addresses.ts`).

### Artifacts

- 7 contracts in `contracts/src/`
- 7 test suites in `contracts/test/`
- `contracts/script/DeployPhase1.s.sol`
- Updated `contracts/deployments/kite-testnet.json`
- Regenerated ABIs in both `packages/contracts-abi/` (TS) and `packages/contracts-abi-py/` (Py)

### Gates

- `forge fmt --check` clean
- `forge test -vv` green
- `forge coverage --report summary` ≥ 85% branch
- ABI regeneration step in CI catches drift

---

## WS2.A — Momentum circuit + verifier (long pole, parallel to WS1, est. 5–7 days)

Branch: `phase-1-circuits`. No dependency on WS1 — pure circom work.

### Constraints (per `Helios.md §9.3`)

1. Asset universe membership for `asset_in` / `asset_out` (Merkle proof against manifest's universe root)
2. `amount_in ≤ max_position_size` (range check)
3. `min_amount_out ≥ amount_in × oracle_price × (1 - max_slippage_bps / 10000)` — fixed-point, careful with rounding
4. Price observations Poseidon-chain to a committed oracle root
5. Direction logic:
   - **Long entry**: N-period return > threshold AND prior position is flat/short
   - **Short entry**: symmetric
   - **Exit**: signal-flip OR stop-loss hit
6. `block_window_end - block_window_start ≤ 100`

### Constraint budget

- Target: ~15k
- Hard ceiling: 20k (PTAU 16 headroom)
- Profile via `circom --inspect momentum_v1.circom` after each major component
- If we hit 18k+ before all constraints are wired, revisit Poseidon arity (use `Poseidon(8)` over 2× `Poseidon(4)`) or split into stage-1 (price commitment) + stage-2 (decision)

### Tests (`circuits/test/momentum_v1.test.js`)

- Valid long entry / short entry / exit (3 happy paths)
- Invalid: amount over cap, asset out of universe, threshold not met, slippage breached, window > 100 blocks
- Boundary: exact threshold hit (must accept), exact threshold - 1 wei (must reject)

### Artifacts

- `circuits/momentum_v1.circom`
- `circuits/momentum_v1.wasm`, `momentum_v1.zkey`, `verification_key.json`
- `contracts/src/verifiers/MomentumV1Verifier.sol` (snarkjs-generated)
- Deploy script `contracts/script/DeployVerifier.s.sol` (parameterized by class)
- Registration call into `TradeAttestationVerifier` (after WS1 deploy)
- Benchmark recorded in `docs/circuit-specs.md` (proof gen p95 on Servarica 2 dedicated cores)

### Gates

- `cd circuits && make momentum_v1 && make test` green
- Constraint count printed in build output ≤ 20k
- Proof gen p95 ≤ 2s on the Servarica box (or local equivalent if box not yet live)
- Round-trip: witness → proof → on-chain verify returns `true`

---

## WS2.B — Service substrate (starts when WS1 + WS2.A merge, est. 5–7 days)

Four near-independent services. Spread across parallel agent contexts or build in sequence — each is small.

### Prover service (`services/prover/`)

- `POST /prove { strategyClass, witnessInputs, publicInputs }` → `{ proof, publicSignals }`
- Load `momentum_v1.wasm` + `momentum_v1.zkey` at startup; class-dispatched table
- Degraded mode: snarkjs error or wall time > 30s → respond 503 with structured error (no silent fallback)
- Integration test: spin up local anvil with `MomentumV1Verifier` deployed, generate proof, on-chain verify returns true
- Pin snarkjs version in `package.json`; record in `docs/circuit-specs.md`

### Oracle service Phase 1 minimum (`services/oracle/`)

- Polls a price source for WKITE / USDC.e / WETH at 1-min cadence
  - **Open question for user**: which source — Algebra Integral pool reads on Kite, or external (Pyth/Chainlink) feed?
- Signs each snapshot with `ORACLE_SIGNER_PK`
- In-memory Poseidon chain; `GET /snapshots/recent?n=N` and `GET /snapshots/root`
- On-chain anchor: simple `OraclePriceAnchor` contract committing root every 5 min (or piggyback on `Helios.sol` heartbeat for Phase 1; full circuit-committed root in Phase 2)
- `SCENARIO_MODE=1` → reads `scenarios/phase1-drawdown.json` instead of polling

### Reputation engine v1 (`services/reputation/`)

- Polls Goldsky every 60s for `TradeAttested`, `NAVReported`, `StrategyDefunded`
- **Phase 1 simplification**: `score = 0.7 × clip(realized_pnl_30d / notional, -1, 1) + 0.3 × proof_validity_rate`
- Sign with `REPUTATION_SIGNER_PK`, post via `ReputationAnchor.postReputationUpdate(strategy, score, sigComponents)`
- WebSocket endpoint for dashboard subscriptions
- Full §8.2 formula deferred to Phase 2

### Subgraph datasources (`subgraph/`)

- Edit `subgraph.yaml`: add 7 contracts deployed in WS1 with their start blocks
- Mappings (`subgraph/src/`):
  - `StrategyRegistered`, `AllocatorRegistered` → registry handlers
  - `AllocationCreated`, `StrategyDefunded`, `RebalanceComplete` → allocator handlers
  - `TradeAttested`, `NAVReported` → strategy vault handlers
  - `ReputationUpdated` → anchor handler
- Entities per `Helios.md §13` schema
- `pnpm --filter subgraph codegen && pnpm --filter subgraph build && pnpm --filter subgraph deploy`
- Set `GOLDSKY_ENDPOINT` and `NEXT_PUBLIC_GOLDSKY_ENDPOINT` in `.env` and Vercel after deploy

### Gates

- Each service: `pytest` / `node --test` green, health endpoint live in `docker-compose.yml`
- Subgraph: indexing lag < 60s on Kite testnet (measured against fresh contract deploys)

---

## WS2.C — Sentinel allocator (starts when WS2.B core lands, est. 5 days)

`services/sentinel/`. Built directly (not on `allocator-sdk` yet — that lands in Phase 3).

### Decision cycle (`Helios.md §11.2`)

1. Read user meta-strategies and current allocations from chain + Goldsky
2. Read latest reputation snapshots
3. Compute candidate ranking: `ReputationScore × CapacityFactor × FeeFactor × ClassFitFactor`
4. Detect breaches (drawdown > meta threshold) → enqueue defunds
5. Compute target allocations per user
6. Submit txs (defunds first, then allocations, then rebalances) batched per block

### Schedulers

- Drawdown check: 60s cadence
- Rank update: 5min cadence
- Rebalance: per user's `rebalanceCadenceSec` (defaults to 1h Conservative / 15min Aggressive)
- Fee crystallization: triggered on NAV > HWM × (1 + FEE_THRESHOLD)

### REST endpoints (`Helios.md §11.3`)

- `POST /v1/users/{user}/meta-strategy` — accept signed meta-strategy
- `GET /v1/users/{user}/dashboard` — composite dashboard payload
- `GET /v1/strategies` — public directory with filters
- `WS /v1/users/{user}/events` — event stream

### Setup

- One-shot script: register Sentinel on `AllocatorRegistry` with `isReferenceBrand=true`, name `"Helios Sentinel"`, fee rate from env (default 400 bps for Phase 1)
- Stake from deployer EOA (testnet KITE)

### Gates

- Decision cycle round-trip < 5s in scenario mode
- All REST endpoints return real data against the local stack
- Auto-defund test passes: simulate breach → assert defund tx submitted within 60s

---

## WS2.D — Reference momentum strategy (starts when WS2.A + Prover live, est. 3 days)

`reference-strategies/momentum_v1/strategy.py`. Built on `helios-strategy-sdk`.

### Behavior (per `Helios.md §10.2`)

- Polls 1-min bars from oracle service (or scenario stream) for assets in `asset_universe`
- `on_bar(asset, snapshot)`:
  - Compute N-period return
  - If signal: build `TradeIntent`, size via `size_trade`, build router calldata
  - Call prover service → `executeWithProof(proof, publicInputs, trades)`
- NAV reporter every 5min (`StrategyVault.reportNAV`)
- Emit events consumed by subgraph

### DEX integration

- Algebra Integral router on Kite testnet — **need to verify calldata format against an existing pool early** (Phase 1 task day 1 of WS2.D)
- Trade slippage cap from manifest; sign as part of public inputs

### Deploy

- `deploy/services/strategy-momentum.Dockerfile` (extends `python.Dockerfile` with `SERVICE_PACKAGE=momentum_v1` etc.)
- Add to `deploy/docker-compose.prod.yml` once stable

### Gates

- A single trade lands on Kite testnet with proof verified by `TradeAttestationVerifier`
- NAV report observable on Goldsky within one indexer cycle

---

## WS3 — Scenario mode + e2e (starts when WS2.C + WS2.D landable, est. 3 days)

### Scenario file (`scenarios/phase1-drawdown.json`)

Deterministic price series shaped:

1. 10 bars flat at $1.00 (warmup)
2. 10 bars rising 0.5% / bar (momentum entry triggers on bar ~15)
3. 5 bars flat at peak (trade settled, allocation in place)
4. 20 bars dropping ~1% / bar → 18% drawdown (breaches default 15% threshold mid-way)
5. 5 bars flat at trough (defund + replacement allocation visible)

### `scripts/e2e-scenario.sh`

1. `docker compose up -d` with `SCENARIO_MODE=1`
2. `forge script DeployPhase1.s.sol --rpc-url anvil-kite --broadcast`
3. Update local `addresses.json`
4. Sentinel registers + reads default meta-strategy
5. Pretend-user: EOA `[PASSPORT-STUB]` signs meta-strategy + deposits 10k mock USDC
6. Wait for first allocation event (timeout 30s)
7. Wait for first `TradeAttested` event (timeout 30s)
8. Continue scenario through drawdown
9. Assert: `StrategyDefunded` event emitted by non-allocator EOA (permissionless path), replacement `AllocationCreated` follows, NAV trace matches expected
10. Tear down

### CI integration

- New CI job `e2e` triggered on every PR
- Skipped if only `frontend/`, `docs/`, `*.md` touched (path filter)
- Caches docker layers

### Gates

- e2e completes < 5 min wall-clock
- Asserts cover both the happy path and the permissionless-defund path

---

## WS4 — Frontend minimum (parallel to WS2 + WS3, est. 6–8 days)

Branch: `phase-1-frontend`. Starts as soon as ABIs are stable post-WS1 freeze. Develops against local anvil; flips to Kite testnet for final verification.

### Pages

1. **`/onboard`** — template picker (Conservative/Balanced/Aggressive), customization panel (asset universe, max per-strategy, drawdown threshold, max fee rate, rebalance cadence), plainspoken commitment summary, EOA wallet sign `[PASSPORT-STUB]`
2. **`/dashboard`** — top strip (total NAV, today's P&L, all-time P&L, fees-to-date), current allocator card, active allocations table, live activity rail (WebSocket to Sentinel), withdraw control always visible
3. **`/strategies`** — public directory table, sortable by every column, filter by class/chain/reputation

### Activity rail

- Renders `StrategyAllocated`, `TradeAttested` (with shield icon), `StrategyDefunded`, `RebalanceComplete`
- Mechanical step-in animation per `DESIGN.md §13` — instant appearance, 80ms tick, no smooth easing
- Defunded row: red left-border per `DESIGN.md §10.2`

### Conventions

- All Passport touchpoints comment-tagged `[PASSPORT-STUB]` referencing `docs/kite-passport-notes.md` swap-in checklist
- Design tokens only — no hardcoded colors in JSX (per `CLAUDE.md` Tailwind rule)
- Reduced-motion media query reduces all motion to instant
- Dark mode only

### Gates

- Lighthouse perf ≥ 85 on `/dashboard` (subgraph response is the critical path)
- Playwright smoke test for the three signature interactions deferred to Phase 4 — Phase 1 just needs the surfaces wired

---

## WS5 — Acceptance & gating (1–2 days at end)

- `forge coverage --report summary` ≥ 85% on Phase 1 contracts (CI gate enforced)
- `scripts/e2e-scenario.sh` green in CI
- **Fresh-clone test**: clone repo to a throwaway machine, `pnpm dev`, run scenario; ≤ 10 min wall-clock end-to-end
- Manual `Helios.md §11.2` walk: confirm decision-cycle order in Sentinel logs
- `DESIGN.md §13` motion budget audit on activity rail (no smooth easings on event-driven elements)
- Tag `v0.1.0-phase1`, write release notes covering acceptance evidence

---

## Calendar (rough)

```
Wk1  WS1 contracts ████████   WS2.A circuit ██████   WS4 FE scaffold ██
Wk2  WS1 (deploy)  █████      WS2.A (verifier deploy) ██   WS2.B services ████   WS4 FE pages █████
Wk3  WS2.C sentinel █████   WS2.D momentum strategy ███   WS4 FE wires to live data ████
Wk4  WS3 scenario+e2e ███   WS5 acceptance ██   buffer ██
```

~4 weeks. Comfortably within the extended hackathon window with buffer for Phase 2 onward.

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Momentum circuit > 20k constraints | Medium | Pushes proof time > 2s, breaks acceptance | Profile after each component (day 2 of WS2.A); reduce Poseidon arity or split circuit if needed |
| Algebra Integral router calldata differs from vanilla | Medium | Strategy can't trade | Verify against existing pool day 1 of WS2.D before writing the rest |
| Goldsky indexing lag spikes | Low | Reputation updates lag → wrong allocator decisions | Add RPC fallback for most-recent block; alert if lag > 60s |
| Snarkjs proof gen too slow on Servarica | Low | Acceptance fails | Benchmark on local (4-core dev box) first; if Servarica is materially slower, add second prover process |
| Permissionless-defund path silently broken | Medium | Demo-critical scenario fails on stage | Explicit non-allocator caller in e2e test; not just "alloctor calls defund" |

## Open questions for user

1. **Oracle price source** — Algebra Integral pool reads on Kite, or external feed (Pyth/Chainlink) bridged in? Phase 1 spec is vague.
2. **Kite testnet deployer key** — need a non-Passport EOA with testnet KITE for `forge script ... --broadcast`. `cast wallet new`, fund from Kite faucet, paste back as `DEPLOYER_PK`.
3. **Sentinel default fee rate** — Phase 1 spec doesn't pin it; I'm proposing 400 bps (4% perf fee). OK or adjust?
4. **Reserved Algebra Integral router address on Kite testnet** — I'll find it from Kite docs but a confirm would speed WS2.D.

## Branch + PR convention

- `phase-1-contracts` — single PR
- `phase-1-circuits` — single PR
- `phase-1-services` — one PR per service (prover, oracle, reputation, subgraph, sentinel, momentum)
- `phase-1-frontend` — one PR per page
- `phase-1-scenario` — single PR last
- PR title format: `[Phase 1][WS1] Implement UserVault + tests`
