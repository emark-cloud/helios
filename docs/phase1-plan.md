# Phase 1 — detailed execution plan

Companion to `TODO.md` Phase 1 section and `Helios.md §6 / §9 / §11`. Read after both. Updated 2026-04-27.

## Status (2026-04-27)

Backend vertical slice **complete**. WS1 + WS2.A–D + WS3 (including Track B live deploy to Kite testnet) all merged to `main`. Contracts live at the addresses in `contracts/deployments/kite-testnet.json` (chainId 2368, deployer `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25`).

Remaining for Phase 1 acceptance:
- **WS4 frontend** — `/onboard`, `/dashboard`, `/strategies` (untouched)
- **WS5 cleanup** — forge coverage ≥85% lines on Phase 1 contracts (✅ 97.54% via `--no-match-coverage "(script|test)/"`, gated in CI); Goldsky subgraph live + indexing Track B addresses (✅ `helios/v0.1.1` 100% synced, graph-ts pinned to 0.31.0); VPS service deploy from `deploy/docker-compose.prod.yml`; fresh-clone 10-min acceptance run; release tag.
- **External carry-over** — Passport smoke test (still BLOCKED per `docs/kite-passport-notes.md`)

## Phase 1 in one sentence

End-to-end vertical slice on Kite testnet: user signs a meta-strategy (EOA-stubbed for Passport) → Sentinel routes capital to a momentum strategy → strategy executes a real Groth16-attested trade → Reputation Engine posts an update → scenario mode drives a drawdown → permissionless `defundStrategy` fires → replacement allocation lands → dashboard reflects every step.

## Working assumptions

1. **Passport is blocked externally** (see `docs/kite-passport-notes.md`). Every Passport touchpoint stubs to EOA + EIP-712 signatures, marked `[PASSPORT-STUB]` in code with a pointer to the swap-in checklist.
2. **Hackathon deadline extended ≥2 weeks.** Use the room to hit 85% coverage and a clean e2e — don't ship Phase 1 with corners cut.
3. ~~**VPS not yet live.**~~ **VPS bootstrapped 2026-04-25** (Servarica Montreal `helios@38.49.216.27`); pm2/compose entry for sentinel + momentum still gated on WS5 deploy hardening, but the box is ready.
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

**Decision (2026-04-25):** Kite docs show no on-chain oracle (Pyth/Chainlink/RedStone) on mainnet or testnet, and no documented Algebra DEX deployment on testnet to read TWAPs from. So the Phase 1 oracle service signs snapshots from an **off-chain price source** (Binance public REST API as primary, Coingecko free tier as fallback) — both are free and need no auth. The on-chain anchor still holds: snapshots are Poseidon-chained and the root is committed periodically.

When Kite testnet gets either Algebra deployment or a real oracle, the price source plugs in behind the same `oracle.sources` interface — service contract doesn't change.

- Pulls 1-min OHLC bars for KITE/USDT, ETH/USDT (BTC/USDT later if used) at 1-min cadence
- Signs each snapshot with `ORACLE_SIGNER_PK`
- In-memory Poseidon chain; `GET /snapshots/recent?n=N` and `GET /snapshots/root`
- On-chain anchor: simple `OraclePriceAnchor` contract committing root every 5 min (or piggyback on `Helios.sol` heartbeat for Phase 1; full circuit-committed root in Phase 2)
- `SCENARIO_MODE=1` → reads `scenarios/phase1-drawdown.json` instead of polling
- Source-abstraction layer (`oracle/sources/binance.py`, `oracle/sources/coingecko.py`, `oracle/sources/scenario.py`, `oracle/sources/algebra.py` (stub for Phase 2)) so swapping later is a config flip

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

**Decision (2026-04-25):** Kite docs list Algebra Integral on mainnet only (factory `0x10253594…`, router `0x03f8B4b1…`, NPM `0xD637cbc2…`). No testnet Algebra deployment is documented. For Phase 1 we deploy a **`MockSwapRouter` + `MockPool`** on Kite testnet to give trades something to settle against. The proof + verifier path stays real; only the DEX layer is mocked. Real Algebra integration is a Phase 2 task — at which point we either get testnet support from the Kite team or move the demo to mainnet.

- `contracts/src/mocks/MockSwapRouter.sol` + `MockPool.sol`: minimal swap interface (token-in → token-out at the oracle's signed price ± configured slippage), emits `Swap` event in the same shape as Algebra
- Strategy builds calldata against `MockSwapRouter` ABI; same calldata structure ports to Algebra later
- Trade slippage cap from manifest; sign as part of public inputs
- **Action item for user:** ping Kite Discord/team to confirm testnet Algebra status — could unblock real DEX integration in WS2.D and skip the mock entirely

### Deploy

- `deploy/services/strategy-momentum.Dockerfile` (extends `python.Dockerfile` with `SERVICE_PACKAGE=momentum_v1` etc.)
- Add to `deploy/docker-compose.prod.yml` once stable

### Gates

- A single trade lands on Kite testnet with proof verified by `TradeAttestationVerifier`
- NAV report observable on Goldsky within one indexer cycle

---

## WS3 — Scenario mode + e2e (starts when WS2.C + WS2.D landable, est. 3 days)

### Direction (decided 2026-04-27)

WS3 has two tracks, sharing a single script:

- **Track A — local anvil-kite (canonical, CI-gated).** Default target. Deterministic, reproducible, gates every PR, satisfies the "fresh clone + scenario in 10 min" Phase 1 acceptance bar. `scripts/e2e-scenario.sh` runs against the `anvil-kite` service in `docker-compose.yml`.
- **Track B — live Kite testnet (one-shot, judge-facing).** Same script invoked as `RPC_URL=$KITE_RPC_URL ./scripts/e2e-scenario.sh`. Broadcasts to Kite testnet, populates `contracts/deployments/kite-testnet.json` with real addresses, gives Goldsky + frontend + judges live tx hashes to verify on OKLink. Run once at WS3 sign-off; **not** in CI.

`Helios.md §6 / §9` stake the marketplace pitch on "go verify it yourself" — Track B is what makes those addresses real. Track A is what keeps the loop tight enough to ship.

### Deferred from WS3 (with reason)

- **Oracle on-chain root anchor.** Phase 1 keccak256 chain is service-local; the momentum circuit doesn't consume the on-chain root yet (Phase 2 swaps in Poseidon and the circuit reads the committed root). `OraclePriceAnchor` deploy is decorative until then — defer to Phase 2.
- **Goldsky deploy in the CI e2e.** CI uses `web3.py` `eth_getLogs` directly against anvil for event assertions — no external dep, no flake surface. Track B follows up with `pnpm --filter subgraph deploy` against the testnet contracts so the dashboard renders against real data; that step is documented but not gated by CI.

### Goldsky verification checklist (post-deploy, 2026-04-27 — v0.1.1)

Subgraph `helios/v0.1.1` is the live deploy. v0.1.0 was deployed first but the indexer rejected the WASM with `SubgraphStartFailure: Unknown opcode 252` (graph-ts 0.36 / `apiVersion: 0.0.9` emit opcode 0xFC bulk-memory ops the Goldsky runtime doesn't support). Pinning to graph-ts `0.31.0` + graph-cli `0.83.0` + `apiVersion: 0.0.7` produced WASM the runtime accepts; v0.1.1 hit 100% synced in <1m. v0.1.0 has been deleted. Endpoint pinned in `.env.example` as `GOLDSKY_ENDPOINT` / `NEXT_PUBLIC_GOLDSKY_ENDPOINT` → `helios/v0.1.1`.

Three checks, cheapest first:

1. **Sync progress.** `pnpm --filter @helios/subgraph exec goldsky subgraph list helios/v0.1.1`. Look for `Synced: 100.00%` (or any > 0%) and `Blocks indexed: 21074384 -> <recent>`. Right-hand side past `21074421` (last deploy block) means all deploy events have been processed.

2. **GraphQL — entities should exist.**
   ```bash
   curl -s -X POST $GOLDSKY_ENDPOINT \
     -H 'Content-Type: application/json' \
     -d '{"query":"{ allocators { id name isReferenceBrand } strategies { id declaredClass } verifierRegistrations { strategyClass verifier } }"}' \
     | python3 -m json.tool
   ```
   Expected once synced (from `DeployPhase1.s.sol`):
   - **3 strategies** — `declaredClass` = keccak("momentum_v1"), keccak("mean_reversion_v1"), keccak("yield_rotation_v1")
   - **1 allocator** — name `"Helios Sentinel-shadow"`, `isReferenceBrand: false` (the reserved `"Helios Sentinel"` is multi-sig only)
   - **3 verifierRegistrations** — one per class, each pointing at a `MockGroth16Verifier` address

   If those three queries return the expected counts, the subgraph is working end-to-end (manifest → ABI → mappings → entities).

3. **If sync is still stuck after an hour, check logs.** `pnpm --filter @helios/subgraph exec goldsky subgraph log helios/v0.1.1 --since 1h --filter warn`. Likely failure mode is finality-related (`block not finalized` or RPC error). If that's what surfaces, options: (a) wait longer for natural finality, (b) ask Goldsky support whether their `kite-ai-testnet` integration uses a finalized-only RPC, (c) lower `startBlock` to a much earlier block to confirm the indexer can backfill at all.

### Six wiring pieces (all in scope, ordered by dependency)

1. **`DeployPhase1.s.sol` writes to canonical path.** Today the script writes `./deployments/<chain>-phase1.json`; WS3 makes it write `contracts/deployments/<chain>.json` so services + subgraph + frontend pick it up unchanged. Default chain name keyed on `block.chainid` (`anvil-kite`, `kite-testnet`, `kite-mainnet`).
2. **Sentinel `services/sentinel/src/sentinel/onchain.py` — live tx path.** web3.py implementation of `allocateToStrategy` / `defundStrategy` / `settleStrategyFee` (and `rebalance` placeholder). `_live` branch currently raises `NotImplementedError`; WS3 wires it.
3. **Momentum `reference-strategies/momentum_v1/src/momentum_v1/executor.py` — live tx path.** web3.py implementation of `executeWithProof` + `reportNAV` against `StrategyVault`. Same dry-run → live posture as Sentinel.
4. **Reputation engine — on-chain submission.** Wire `REPUTATION_ANCHOR_ADDRESS` so signed scores reach `postReputationUpdate(strategy, score, sigComponents)`. Engine already signs; just needs the transact path.
5. **`scripts/e2e-scenario.sh`** — boot, deploy, address-load, fund a `[PASSPORT-STUB]` user EOA + a *separate* non-allocator EOA (the permissionless-defund caller), drive the scenario through the drawdown, assert via `eth_getLogs`.
6. **CI job in `.github/workflows/ci.yml`** — path-filtered to skip frontend/docs-only PRs, docker layer caching, ≤5 min wall-clock target.

### Scenario file (`scenarios/phase1-drawdown.json`)

Already committed in WS2.B (16-bar KITE drawdown ~7%, ETH flat). WS3 may extend if the existing series doesn't trip the default 15% drawdown threshold under the configured meta-strategy — adjustment is a config tweak, not a redesign.

### `scripts/e2e-scenario.sh` (Track A flow)

1. `docker compose up -d postgres redis anvil-kite prover`
2. `forge script DeployPhase1.s.sol --rpc-url $RPC_URL --broadcast` (defaults to `http://localhost:8545`)
3. Read `contracts/deployments/<chain>.json`; export addresses as env vars consumed by services
4. Boot oracle / sentinel / reputation / momentum-strategy as background processes (or pm2 / `uv run --package …`) with `SCENARIO_MODE=1` and the address env vars
5. Sentinel registers itself on `AllocatorRegistry` (already in deploy script as `Helios Sentinel-shadow`); reads default meta-strategy from a fixture
6. Pretend-user EOA `[PASSPORT-STUB]` signs meta-strategy + deposits 10k mock USDC + delegates capital to AllocatorVault
7. `eth_getLogs` poll for first `AllocationCreated` (timeout 30s)
8. `eth_getLogs` poll for first `TradeAttested` (timeout 60s — proof gen + tx confirm)
9. Drive oracle scenario clock to the drawdown bars; wait for sentinel to detect breach OR call `defundStrategy` from a **non-allocator** EOA (test the permissionless path explicitly)
10. Assert: `StrategyDefunded` event with `caller != AllocatorVault.operator`; replacement `AllocationCreated` follows within rebalance cadence
11. Tear down

### Gates

- e2e completes < 5 min wall-clock against Track A
- **Permissionless-defund is a hard gate** (`Helios.md §6.3` keystone): the test must call `defundStrategy` from an EOA that is not Sentinel's operator and assert the tx lands. "Sentinel calls defund" is not sufficient.
- Track B run produces a populated `contracts/deployments/kite-testnet.json` checked into the repo

### CI integration

- New `e2e` job in `.github/workflows/ci.yml` triggered on every PR
- Skipped if only `frontend/`, `docs/`, `*.md` touched (path filter)
- Caches docker layers
- Runs Track A only — Track B is a manual sign-off step

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

## Calendar (actual)

```
Wk1  WS1 contracts ████████ ✅   WS2.A circuit ██████ ✅
Wk2  WS1 (deploy) ✅              WS2.A (verifier) ✅              WS2.B services ████ ✅
Wk3  WS2.C sentinel █████ ✅      WS2.D momentum ███ ✅
Wk4  WS3 scenario+e2e ███ ✅      WS5 acceptance ░░ (open)         WS4 FE ░░░░ (open)
```

Backend tracks landed inside the calendar window. WS4 frontend slipped (parallel work was deferred while backend cleared); WS5 acceptance gates carry forward as a slim closing pass. Buffer remains for Phase 2 onward.

## Risks & mitigations (open)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Goldsky indexing lag spikes | Low | Reputation updates lag → wrong allocator decisions | Add RPC fallback for most-recent block; alert if lag > 60s. *Still open — surfaces once subgraph deploys against testnet addresses.* |
| Frontend slip eats WS5 buffer | Medium | Phase 1 acceptance pushes into Phase 2 calendar | Scope WS4 to the three pages on the acceptance list (`/onboard`, `/dashboard`, `/strategies`); defer sunburst + signature interactions to Phase 4 per existing plan |

## Resolved

| Risk / question | Resolution |
|---|---|
| Momentum circuit > 20k constraints (was Medium) | **5378 non-linear constraints** (≈27% of ceiling) — well under budget. (WS2.A) |
| Snarkjs proof gen too slow on commodity hardware (was Low) | **~1.5s on dev box**, well under 2s target. VPS bench will revisit but headroom is large. (WS2.B) |
| Permissionless-defund path silently broken (was Medium) | **Hard-gated by WS3 e2e** — `StrategyDefunded` must be emitted by an EOA that is *not* Sentinel's operator, asserted via `eth_getLogs` in `scripts/e2e_scenario.py`. (WS3) |
| Algebra Integral router calldata differs from vanilla (was Medium) | **Mooted for Phase 1.** No documented Algebra deployment on Kite testnet (memory: `reference_kite_contract_surface`). Phase 1 ships against `MockSwapRouter`; mainnet promotion in Phase 6 swaps in real router (`docs/deployment-strategy.md`). |
| Oracle price source (open 2026-04-25) | Binance REST → Coingecko fallback; Phase 1 keccak256 chain (Solidity-native), Phase 2 swaps to Poseidon so the momentum circuit can consume the on-chain root directly. (WS2.B) |
| Sentinel default fee rate (open 2026-04-25) | 400 bps (4% perf fee) approved. |
| DEX target (open 2026-04-25) | `MockSwapRouter` + `MockPool` on testnet; real Algebra deferred to Phase 6 mainnet promotion. |
| `DEPLOYER_PK` (open 2026-04-25) | Provided. Address `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25`. Track B deploy 2026-04-27 spent ~0.000017 KITE of the 0.5 KITE budget — plenty of headroom for any redeploy or testnet ops. |
| Live deploy to Kite testnet (gated on WS3) | **Track B sign-off 2026-04-27** — `contracts/deployments/kite-testnet.json` populated with real addresses; broadcast log preserved at `contracts/broadcast/DeployPhase1.s.sol/2368/run-latest.json`. Required `forge script --skip-simulation` (testnet RPC rejects pre-finality state queries). |

## Open

- ~~**Goldsky subgraph deploy**~~ — Resolved 2026-04-27 (WS5). `helios/v0.1.1` synced 100% against Track B addresses; graph-ts pinned to 0.31.0 to dodge the apiVersion 0.0.9 opcode-252 incompatibility.
- **Confirm testnet Algebra status with Kite team** — still nice-to-have so we can drop the mock router earlier than Phase 6, but no longer blocking.

## Branch + PR convention

- `phase-1-contracts` — single PR
- `phase-1-circuits` — single PR
- `phase-1-services` — one PR per service (prover, oracle, reputation, subgraph, sentinel, momentum)
- `phase-1-frontend` — one PR per page
- `phase-1-scenario` — single PR last
- PR title format: `[Phase 1][WS1] Implement UserVault + tests`
