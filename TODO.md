# Helios — Phased Implementation Checklist

Mirrors the build plan at `/home/emark/.claude/plans/i-want-to-start-jiggly-hare.md`. Check items as they land. Each phase has an **Acceptance** section — do not declare a phase done until every acceptance criterion passes.

Tracks: **CX** (contracts/circuits), **SX** (services/SDKs), **FE** (frontend/bot), **OP** (infra/ops).

Current phase: **Phase 4** (Phases 0–3 complete as of 2026-05-06).

---

## Phase 0 — Bootstrap & ground truth ✅ (done 2026-04-25, modulo user-action items below)

**Goal.** Empty repo → working dev loops for every layer, frozen interface contracts, infra accounts ready.

### Outstanding (requires user action — does not block Phase 1 scaffolding)
- [x] Goldsky account + `GOLDSKY_API_KEY` provisioned; CLI pinned in `subgraph/package.json`, project "Helios" reachable. Full `pnpm --filter subgraph deploy` runs in Phase 1 once `subgraph.yaml` has datasources.
- [x] Vercel project `helios-frontend` linked to `emark-cloud/helios` (root `frontend/`, production = `main`); preview deploys auto-fire on PRs. `VERCEL_TOKEN` in `.env`. See `deploy/vercel-notes.md`.
- [x] VPS reservation — Servarica Montreal (8 GB / 2 dedicated cores / 250 GB NVMe, Ubuntu 24.04.4 LTS) at `helios@38.49.216.27`. Bootstrap complete: Docker 29.4 / Node 20.20 / PM2 5.4 / nginx 1.24 installed; helios user created with sudo+docker; UFW restricts to 22/80/443; 2 GB swap; sshd hardened to key-only auth (password auth blocked at protocol level). SSH key at `~/.ssh/helios_vps`. Deploy services via `pm2 start deploy/ecosystem.config.cjs` once Phase 1 services are ready.
- [x] **Unblocked 2026-04-30** — Kite mainnet went live 2026-04-28 (chain 2366); Passport public via `kpass` CLI + `@gokite-network/auth` widget + `gokite-aa-sdk`. SDK-tarball spike (2026-04-30) confirmed three things that diverge from the v0 spec: (a) **no BIP-32 hierarchical session-key delegation** in the AA SDK — cascade authority must be enforced in Solidity ACL, not in identity-derivation; (b) the user-onboarding surface is **`@gokite-network/auth`** (Particle-Network-backed embeddable widget), distinct from the **`kpass` CLI** which targets AI-agent x402 flows; (c) the AA wallet supports arbitrary contract calls, so the funding flow into `UserVault` is a single batched userOp. Spec rewrite landed in `Helios.md` (§1.3, §2.1, §3, §4, §5.1, §6.2, §7.2, §11.3, §12.1, §14.1, §15) and `docs/kite-passport-notes.md`. Live `/onboard` integration is Phase 4 work — see Phase 4 §"FE — Passport onboarding rebuild" below.

### OP — Infra & scaffolding
- [x] Initialize monorepo at `/home/emark/helios/` with `pnpm` workspace + `uv` Python workspace
- [x] `.gitignore`, `.editorconfig`, `.env.example`, `LICENSE` (MIT or Apache-2.0)
- [x] Set up GitHub repo + branch protection on `main`
- [x] CI pipeline: Foundry tests + `forge fmt --check` + `ruff` + `pyright` + TS typecheck on every PR
- [x] `docker-compose.yml` boots: Postgres, Kite dev RPC (or anvil fork), anvil forks for Base/Arbitrum, Redis (for service coordination)
- [x] `.env.example` enumerates every variable listed in `CLAUDE.md`

### CX — Contracts & circuits scaffold
- [x] Foundry init at `contracts/` with `foundry.toml`, remappings, `forge-std`, `openzeppelin-contracts-upgradeable`, `@layerzero/oapp`
- [x] Hello-world contract (`Helios.sol` placeholder), deployed to Kite testnet via `script/Deploy.s.sol`
- [x] Address recorded in `contracts/deployments/kite-testnet.json`
- [x] Circom 2.1.9+ toolchain + snarkjs installed; `Makefile` builds a trivial `hello.circom` to `.wasm` + `.zkey` + `Verifier.sol`
- [x] Trivial verifier deployed to Kite testnet; `scripts/verify-hello.js` generates a proof and the on-chain call returns `true`
- [x] Local Powers of Tau 16 ceremony artifacts committed under `circuits/ptau/` (or fetched from trusted mirror)

### CX — Contract interface freeze
- [x] Define Solidity interfaces for all 7 contracts in `contracts/src/interfaces/` — function signatures, events, structs, errors per `Helios.md §6`
- [x] Generate ABIs from the interface artifacts
- [x] `packages/contracts-abi/` publishes the ABIs as both TypeScript (for frontend + subgraph codegen) and Python (for services + SDKs)
- [x] `packages/contracts-abi/schemas/` exports TypeScript types for every event payload
- [x] Downstream packages (`strategy-sdk`, `allocator-sdk`, `frontend`, `subgraph`) all import from this package — no ABI fragments elsewhere

### SX — Service skeletons
- [x] FastAPI scaffold template (`services/_template/`) with structlog, pydantic v2, SQLAlchemy, pytest
- [x] `services/sentinel`, `services/reputation`, `services/oracle`, `services/bot` initialized from the template with health endpoints only
- [x] `services/prover/` Node.js scaffold with snarkjs + express, `POST /prove` stub that echoes the request
- [x] Postgres schema v0: `users`, `strategies`, `allocators`, `allocations`, `trades`, `nav_snapshots`, `reputation_snapshots`, `events` tables
- [x] Alembic (or equivalent) migrations set up

### SX — SDK skeletons
- [x] `packages/strategy-sdk` with `pyproject.toml`, base `StrategyAgent` class (abstract methods only), `MarketSnapshot`, `TradeIntent`, `Direction` types
- [x] `packages/allocator-sdk` with `pyproject.toml`, base `BaseAllocator` class, `MetaStrategy`, `StrategyCandidate`, `AllocationTarget` types
- [x] `packages/helios-cli` entry point with `helios --help` showing subcommand stubs (`backtest`, `deploy`, `stake`, `simulate`, `test-proof`)

### FE — Frontend scaffold
- [x] `frontend/` Next.js 14 App Router + TypeScript + Tailwind + shadcn-adjacent component primitives
- [x] Design tokens in `frontend/src/styles/tokens.css` — charcoal/deep-navy base, single amber accent, green/red data-signal colors, chain indicator colors (per `DESIGN.md §4.3`)
- [x] Type pairing chosen and wired (not Inter, not Roboto, not SF Pro — `DESIGN.md §4.4`); monospace with tabular figures for numerics
- [x] wagmi v2 + viem configured with Kite testnet as primary chain (Base + Arbitrum stubs); MetaMask, Coinbase Wallet, Rabby supported
- [x] `/` landing placeholder renders with design tokens visible; dark mode only; WCAG AA pairs
- [x] Reduced-motion media query respected from day one

### CX — Kite Passport smoke test
- [x] `@gokite/aa-sdk` integrated in a script (or frontend route) that mints a Passport, derives a session key, and sends a userOp (live-testnet run pending — see Outstanding)
- [x] Document the exact SDK version and any workarounds in `docs/kite-passport-notes.md`

### Acceptance for Phase 0
- [x] `pnpm dev` boots the full stack locally with zero manual steps
- [x] `forge test -vv` passes the hello-world contract suite
- [x] `cd circuits && make hello && node scripts/verify-hello.js` generates a proof and the verifier contract returns `true`
- [ ] A Passport-signed userOp is confirmed on Kite testnet (tx hash recorded in `docs/kite-passport-notes.md`) — pending user-supplied signer key
- [x] `packages/contracts-abi/` is imported by at least two downstream packages
- [x] CI passes on an empty PR

---

## Phase 1 — Vertical slice on Kite

**Goal.** One full end-to-end thread: user signature → ZK-attested momentum trade → reputation update → scenario-driven drawdown → auto-defund → reallocation. Kite only. Momentum only. Sentinel only.

**Status (2026-04-27).** Backend vertical slice **complete**: WS1 (contracts), WS2.A (momentum circuit), WS2.B (services: prover/reputation/oracle/subgraph), WS2.C (Sentinel), WS2.D (momentum strategy), WS3 (scenario + e2e, including Track B live deploy to Kite testnet), and WS4 (frontend: `/onboard`, `/dashboard`, `/strategies` + shared chrome) all merged to `main`. WS5 cleanup is **in progress** on `phase-1-cleanup` — Phase 0 Hello vestige retired; `forge coverage` aggregate now 97.54% lines (gated ≥85% in CI); Goldsky `helios/v0.1.1` synced 100% against Track B addresses. Remaining: fresh-clone 10-min acceptance test; Lighthouse perf gate on `/dashboard`; manual decision-cycle + motion-budget audit; release tag. **VPS service deploy deferred to Phase 6** (decision 2026-04-27 — TLS + signer-key registration + Dockerfile shims are Phase 6 deploy-hardening work). Passport unblocked 2026-04-30 (mainnet live, SDK spike landed) — `[PASSPORT-STUB]` migration is now Phase 4 work; see Phase 4 §"FE — Passport onboarding rebuild".

### CX — Contracts ✅ (merged to main 2026-04-25 — WS1)
- [x] `UserVault.sol` — MetaStrategy struct, `setMetaStrategy`, `deposit`, `delegateToAllocator(sessionTTL)`, `withdraw`, `settleAllocatorFee`. UUPS upgradeable.
- [x] `AllocatorVault.sol` — AllocationRecord struct, `allocateToStrategy`, `defundStrategy` (permissionless when drawdown breached), `rebalance`, `settleStrategyFee`, `withdrawAllocatorFees`.
- [x] `StrategyVault.sol` — StrategyManifest, `executeWithProof(proof, publicInputs, trades)`, `reportNAV`, `distributeRealized`, `withdrawToAllocator`, `slash`.
- [x] `StrategyRegistry.sol` — `registerStrategy`, `topUpStake`, `withdrawStake` (7-day cooldown), `deactivate`, `updateReputation`, `slash`.
- [x] `AllocatorRegistry.sol` — `registerAllocator`, reserved-name enforcement for `"Helios Sentinel"` + `"Helios Helix"`, `isReferenceBrand`, same stake/cooldown/slash pattern.
- [x] `ReputationAnchor.sol` — `postReputationUpdate` (signer-gated), `postCrossChainUpdate` (OApp-gated, but OApp stub for now), `ActorType` enum.
- [x] `TradeAttestationVerifier.sol` — registry of per-class verifier addresses, `verify(class, proof, publicInputs)`.
- [x] Foundry tests per contract — happy paths, revert paths, out-of-bounds delegation, drawdown-breach permissionless defund, stake cooldown, reserved-name attempt → revert. **162 tests passing.**
- [x] Foundry coverage ≥ 85% across all Phase 1 contracts. *(WS5 cleanup: HelloVerifier + Phase 0 `Helios.sol` placeholder retired; CI gates aggregate line coverage ≥85% via `forge coverage --no-match-coverage "(script|test)/"`. Current: 97.54% lines / 94.04% statements / 95.19% funcs / 74.69% branches.)*
- [x] Deploy script `contracts/script/DeployPhase1.s.sol` + recorded addresses in `deployments/kite-testnet.json`. *(script written; live deploy to Kite testnet pending — runs as part of WS3 e2e.)*

### CX — Momentum circuit ✅ (merged to main 2026-04-25 — WS2.A)
- [x] `circuits/momentum_v1.circom` implements constraints per `Helios.md §9.3`:
  - [x] `asset_in` / `asset_out` in manifest asset universe
  - [x] `amount_in ≤ max_position_size`
  - [x] `min_amount_out` respects max slippage (manifest-bounded)
  - [x] `price_observations` Poseidon-hash to a committed oracle root
  - [x] Direction-specific constraints (long entry: N-period return > threshold + flat/short precondition; short entry: symmetric; exit: signal-flip or stop-loss true)
  - [x] `block_window_end - block_window_start ≤ 100`
- [x] Constraint count ≤ 20k (target ~15k). **5378 non-linear constraints — well under ceiling.**
- [x] Unit tests covering: valid long entry, valid short entry, valid exit, invalid (amount over cap), invalid (asset out of universe), invalid (threshold not exceeded), boundary (exact threshold). **13 witness tests + 4 on-chain round-trip tests passing.**
- [x] `MomentumV1Verifier.sol` generated via snarkjs, on-chain verify proven via `MomentumV1VerifierAdapter`. *(Live deploy to Kite testnet + registration on `TradeAttestationVerifier` runs in WS3 e2e.)*
- [ ] Proof generation p95 ≤ 2s on commodity VPS. *(Bench runs once VPS prover is up.)*

### SX — Prover Service ✅ (merged to main 2026-04-26 — WS2.B)
- [x] `POST /prove` accepts `{ strategyClass, witnessInputs }`, returns `{ proof, publicSignals }`
- [x] Loads `momentum_v1.wasm` + `momentum_v1.zkey` at startup; class-dispatched (`hello`, `momentum_v1`)
- [x] Degraded-mode behavior: if snarkjs crashes or takes >30s, respond 503; no silent fallback. **snarkjs pinned to exact `0.7.6` (couples to MomentumV1Verifier.sol scaffold).**
- [x] Integration test: prover round-trips a real momentum_v1 proof; off-chain `groth16.verify` against the same vkey the on-chain `MomentumV1Verifier.sol` was generated from. **5 tests passing; proof gen ~1.5s on dev box.** *(Live anvil + on-chain verify is covered in WS3 e2e — `MomentumV1Verifier.t.sol` already certifies on-chain acceptance for any proof that passes off-chain verify against this vkey.)*

### SX — Strategy Service (momentum reference) ✅ (merged to main 2026-04-26 — WS2.D, live tx path wired in WS3)
- [x] Polls 1-minute bars for WKITE, USDC.e, WETH from a configured price source (Helios oracle for Phase 1). **`runtime.py` ticks `oracle_client` per asset.**
- [x] `on_bar(asset, snapshot)` implements momentum per `Helios.md §10.2`. **`strategy.py` — N-period return + threshold + flat/short precondition.**
- [x] Constructs trade calldata for the Algebra Integral DEX router. *Phase 1 targets `MockSwapRouter` (Algebra not on Kite testnet — see memory `reference_kite_contract_surface`); same calldata shape, swap-in is a Phase 6 mainnet promotion concern.*
- [x] Calls prover, then `StrategyVault.executeWithProof`. **`executor.py` live path landed in WS3 (web3.py + 256-byte proof bytes).**
- [x] Reports NAV every 5 minutes. **`reportNAV(total_nav_e18, ts, sig)` live path also landed in WS3; OZ v5 ECDSA `v + 27` correction applied.**
- [x] Emits events consumed by subgraph. **`TradeAttested` + `NAVReported` indexed in `subgraph/src/strategy-vault.ts`.**
- [ ] Deploy to VPS via `deploy/services/strategy-momentum.Dockerfile`. *Deferred to Phase 6 deploy-hardening (decision 2026-04-27, WS5): per-service Dockerfile shims, TLS termination, and signer-key registration on-chain are all genuinely Phase 6 work; hackathon judge surface doesn't need Helios services on a public box.*

### SX — Sentinel (reference allocator) ✅ (merged to main 2026-04-26 — WS2.C, live tx path wired in WS3)
- [x] Loop implements the six-step decision cycle from `Helios.md §11.2`. **`loop.py` — read-state → drawdown-check → rank → diff → emit → submit.**
- [x] Ranking function (`Helios.md §8.3`): `ReputationScore × CapacityFactor × FeeFactor × ClassFitFactor`. **`allocator.py`.**
- [x] Drawdown check on 60s cadence. **`loop.py` 60s tick; permissionless-defund path certified by WS3 e2e hard gate.**
- [x] Rank update on 5-minute cadence; rebalance per user's `rebalanceCadenceSec`.
- [x] Fee crystallization on NAV > HWM × (1 + FEE_THRESHOLD). **`settle_fee` call wired through `onchain.py`.**
- [x] REST endpoints: `POST /v1/users/{user}/meta-strategy`, `GET /v1/users/{user}/dashboard`, `GET /v1/strategies`, `WS /v1/users/{user}/events`. **`service.py` + `schemas.py`.**
- [x] Registered on `AllocatorRegistry` with `isReferenceBrand = true`, name `"Helios Sentinel"`. *Phase 1 deploy registers as `"Helios Sentinel-shadow"` — the reserved name `"Helios Sentinel"` is multi-sig-only on the registry; shadow handle is the documented EOA-deployment alias and is wired in `DeployPhase1.s.sol`.*

### SX — Reputation Engine (v1 placeholder) ✅ (merged to main 2026-04-26 — WS2.B, on-chain submission wired in WS3)
- [x] Consumes Goldsky strategy rollups (polling every 60s, 30-day window).
- [x] **Phase 1 simplification**: `score_e4 = round(10_000 × (0.7 × clip(realized_pnl_30d/notional, -1, 1) + 0.3 × proof_validity_rate))`. Full §8.2 formula deferred to Phase 2.
- [x] Sign updates with `REPUTATION_SIGNER_PK` (EIP-712 typehash `ReputationUpdate(...)`, domain `("HeliosReputationAnchor", "1", chainId, anchor)`). On-chain `postReputationUpdate` submission lands in WS3 once `REPUTATION_ANCHOR_ADDRESS` is set; until then engine signs + broadcasts but does not transact.
- [x] WebSocket fanout (`/v1/scores/stream`) plus REST (`/v1/scores/recent`, `/v1/scores/{strategy}`). 14 tests covering score formula bounds + clipping, EIP-712 sign+recover round-trip, engine tick → fanout → cache, REST endpoints.

### SX — Oracle (Phase 1 minimum) ✅ (merged to main 2026-04-26 — WS2.B; on-chain root anchor deferred to Phase 2 — see WS3 deferred list)
- [x] Price oracle signs 1-minute snapshots for KITE/USDT, ETH/USDT (BTC/USDT mapping ready). **Source-abstraction layer (`oracle/sources/{base,binance,coingecko,scenario,algebra}.py`) — Binance → Coingecko fallthrough live; Algebra is a Phase 2 stub. EIP-191-framed ECDSA signature over `keccak256(asset_hash ‖ price_e18 ‖ ts_ms)` with `ORACLE_SIGNER_PK`.**
- [x] Chain of last N snapshots exposed via HTTP. **`GET /v1/snapshots/recent?asset=…&n=…`, `GET /v1/snapshots/root?asset=…&n=…`. Phase 1 used a keccak256 chain (Solidity-native); Phase 2 WS1.A swapped to a Poseidon chain over `price_e18` field elements so the momentum / mean-reversion / yield-rotation circuits consume the root directly without an extra hash-equivalence proof. `root` is now the decimal field element; `root_bytes32` carries the contract-friendly hex.**
- [x] Root committed on-chain — **Phase 2 WS1.A**: `OraclePriceAnchor` (EIP-712 append-only ledger) + `PriceAnchorScheduler` (interval-N commits) wired into the oracle service via `Poller.on_snapshot`. Live submission gated on `ORACLE_PRICE_ANCHOR_ADDRESS`; the address gets populated by `DeployPhase2.s.sol` (WS3.B), at which point the service auto-promotes from dry-run to broadcasting.
- [x] `SCENARIO_MODE=1` replays `scenarios/phase1-drawdown.json` (16-bar KITE drawdown ~7%, ETH flat). 12 service+source+state tests passing.

### SX — Subgraph ✅ (merged to main 2026-04-26 — WS2.B; Goldsky deploy is a Track B follow-up)
- [x] `subgraph.yaml` indexes Kite testnet contracts (7 datasources: StrategyRegistry, AllocatorRegistry, ReputationAnchor, TradeAttestationVerifier, StrategyVault, AllocatorVault, UserVault). *Addresses are placeholders; `DeployPhase1.s.sol` rewrites them from `contracts/deployments/kite-testnet.json` in WS3 e2e.*
- [x] Entities: `User`, `Deposit`, `Allocator`, `Strategy`, `Allocation`, `Trade`, `NAVSnapshot`, `ReputationSnapshot`, `DefundEvent`, `CrossChainReputationMessage`, `VerifierRegistration`. **`pnpm --filter subgraph codegen && build` green.**
- [x] Mappings cover: `StrategyRegistered/Deactivated/ReputationUpdated`, `AllocatorRegistered/Deactivated/ReputationUpdated/ReferenceBrandAssigned`, `ReputationPosted`/`CrossChainReputationPosted`, `TradeAttested`/`NAVReported`/`Slashed`, `AllocationCreated/Increased/Decreased`/`StrategyDefunded`, `MetaStrategySet`/`Deposited`/`AllocatorDelegated`, `VerifierRegistered`. *`Allocation.capitalDeployed` carries the latest event amount, not a running sum — graph-ts 0.36 strict-null inference fights BigInt accumulation in mappings; the dashboard sums events at query time. Phase 2 reintroduces running totals via @aggregation once we upgrade graph-ts.*
- [x] Deployed to Goldsky; read endpoint wired to services + frontend. *v0.1.0 deployed 2026-04-27 stuck at 0% sync (graph-ts 0.36 / `apiVersion: 0.0.9` emitted WASM with opcode 0xFC the Goldsky runtime rejected — `Failed to start subgraph, code: SubgraphStartFailure, error: "Unknown opcode 252"`). Re-deployed 2026-04-27 as `helios/v0.1.1` with graph-ts 0.31.0 / graph-cli 0.83.0 / `apiVersion: 0.0.7`; synced to 100% in <1m. v0.1.0 deleted. Endpoint pinned in `.env.example` as `helios/v0.1.1`. Indexed at deploy: 3 strategies, 1 allocator (`Helios Sentinel-shadow`), 3 verifier registrations.*

### SX — Scenario mode + e2e ✅ (merged to main 2026-04-27 — WS3, Track B sign-off 2026-04-27)

WS3 direction (decided 2026-04-27, see `docs/phase1-plan.md` WS3 section): two tracks share one script. **Track A** (local anvil-kite) is canonical, gates CI, satisfies the 10-min cold-start acceptance bar. **Track B** (`RPC_URL=$KITE_RPC_URL ./scripts/e2e-scenario.sh`) broadcasts to Kite testnet once at sign-off, populates `contracts/deployments/kite-testnet.json`, gives judges live tx hashes per `Helios.md §6 / §9`.

- [x] `services/oracle` supports `SCENARIO_MODE=1` env that replays a deterministic price series from `scenarios/phase1-drawdown.json`
- [x] `DeployPhase1.s.sol` writes addresses to `contracts/deployments/<chain>.json` (canonical path consumed by services + subgraph + frontend), keyed on `block.chainid`
- [x] Sentinel `services/sentinel/src/sentinel/onchain.py` — replace `_live` `NotImplementedError` with web3.py submission of `allocateToStrategy` / `defundStrategy` / `settleStrategyFee`
- [x] Momentum `reference-strategies/momentum_v1/src/momentum_v1/executor.py` — replace `_live` `NotImplementedError` with web3.py submission of `executeWithProof` + `reportNAV`
- [x] Reputation engine — wire `REPUTATION_ANCHOR_ADDRESS` so signed scores reach `postReputationUpdate`
- [x] Scenario: momentum strategy allocated → price drops to trigger drawdown threshold → auto-defund fires (permissionless path) → replacement strategy takes the capital
- [x] `scripts/e2e-scenario.sh` runs the full stack in scenario mode against Track A and asserts the expected end state via `eth_getLogs`
- [x] **Hard gate (`Helios.md §6.3`):** `StrategyDefunded` is emitted by an EOA that is not Sentinel's operator (permissionless-defund explicitly tested, not implied)
- [x] Track B sign-off: one live deploy to Kite testnet, populated `contracts/deployments/kite-testnet.json` checked in (chainId 2368, deployer `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25`, deployed 2026-04-27)
- [x] Runs in CI as the end-to-end integration test (Track A only; path-filtered to skip frontend/docs-only PRs)

**Deferred from WS3 (with reason):**
- Oracle on-chain root anchor — ~~Phase 1 keccak256 chain is service-local; momentum circuit doesn't consume the on-chain root until Phase 2 swaps to Poseidon. `OraclePriceAnchor` deploy is decorative until then.~~ **Resolved by Phase 2 WS1.A**: Poseidon swap landed, `OraclePriceAnchor` + `OracleYieldAnchor` shipped with EIP-712 commits and Foundry tests; WS3.B's `DeployPhase2.s.sol` flips the live anchor address.
- Goldsky subgraph deploy in the CI e2e — CI uses `eth_getLogs` directly. `pnpm --filter subgraph deploy` is a documented Track B follow-up so the dashboard renders against testnet, not a CI gate.

### FE — Frontend minimum (WS4)

Branch: `phase-1-frontend`. PR per page per `docs/phase1-plan.md` convention. Build order: shared chrome → `/strategies` (read-only, easiest) → `/onboard` (wallet sign) → `/dashboard` (most complex). Sunburst deferred to Phase 4 (confirmed 2026-04-27 — DESIGN.md §11 lists it on `/dashboard` but WS4's 6–8d budget can't absorb the bespoke d3/Nivo work; phase1-plan.md WS4 page list already omits it).

**Shared chrome (WS4.0)** — prerequisite for every page:
- [x] Top nav with `G D` / `G S` / `G O` hotkeys + `?` discoverability per `DESIGN.md §5.5`
- [x] App shell layout: dark-mode-only, generous page margins, "four questions" header slot per `DESIGN.md §5.7`
- [x] `ChainBadge`, `ProofBadge` (acknowledged-tier shield per `DESIGN.md §12`), `Numeric` formatter (mono + tabular figures), restyled inline-SVG icon set
- [x] Goldsky GraphQL client over TanStack Query (reads `NEXT_PUBLIC_GOLDSKY_ENDPOINT`)
- [x] Sentinel REST + WS client (reads `NEXT_PUBLIC_SENTINEL_URL`); graceful empty states when unreachable
- [x] Address loader from `contracts/deployments/<chain>.json` (direct JSON import; the contracts-abi addresses module is empty until its generate step runs)

**Pages:**
- [x] `/strategies` — public directory table, sortable by every column, filter by class/chain; row click → Kitescan address page (Phase 4 swaps to `/strategies/[id]`)
- [x] `/onboard` — template picker (Conservative/Balanced/Aggressive), customization panel (asset universe, max per-strategy, drawdown threshold, max fee rate, rebalance cadence, max strategies), plainspoken commitment summary, EOA `personal_sign` tagged `[PASSPORT-STUB]` per `docs/kite-passport-notes.md`
- [x] `/dashboard` — top strip (total NAV, capital deployed, all-time P&L, fees-to-date), current allocator card, active allocations table, live activity rail (WS to Sentinel), withdraw control always visible (button disabled — Phase 2 wires the tx)

**Cross-cutting requirements:**
- [x] Activity rail renders `ALLOCATION_CREATED` (with shield), `STRATEGY_DEFUNDED`, `REBALANCE_COMPLETE`, fee/meta events with mechanical motion (instant entry, 80ms stagger) per `DESIGN.md §13`
- [x] Defunded row + defund-event gets red left-border per `DESIGN.md §10.2` (`[data-defund-state="breaching"]`)
- [x] Reduced-motion media query collapses rail stagger to instant
- [x] All Passport touchpoints comment-tagged `[PASSPORT-STUB]`
- [x] Tokens-only — no hardcoded colors in JSX (per `CLAUDE.md` Tailwind rule)
- [x] No sunburst yet (Phase 4)

**Gates:**
- [x] Lighthouse perf ≥ 85 on `/dashboard` against the local stack. *Measured 2026-04-27 (WS5): Perf 94 / FCP 0.8s / LCP 2.0s / TBT 250ms / CLS 0 / SI 0.8s on a warm `pnpm start` server, headless Chromium via Playwright cache. (Cold-start JIT inflates TBT to ~890ms on the first hit; warm-process measurement is the realistic one.) Phase 4 §14.5 will revisit when the sunburst lands — wagmi provider hydration is the dominant blocking work, candidate for lazy-loading on the wallet-touch path only.*
- [x] Playwright signature-interaction smoke deferred to Phase 4 — Phase 1 just needs surfaces wired
- [x] `pnpm --filter frontend typecheck` + `lint` + `next build` green

### Acceptance for Phase 1
- [ ] Signature-to-first-trade in <60s in scenario mode
- [ ] Auto-defund scenario runs end-to-end with no manual intervention: Passport signature → UserVault deploy → Sentinel allocation → momentum strategy executes `executeWithProof` with real Groth16 proof → `TradeAttested` emitted → Reputation Engine posts update → scenario drives drawdown → `defundStrategy` fires (permissionless path tested) → replacement allocation lands → dashboard reflects every step
- [x] `forge coverage` ≥ 85% on Phase 1 contracts (97.54% lines, gated in CI)
- [ ] A fresh clone + `pnpm dev` + scenario run succeeds on a clean laptop within 10 minutes

---

## Phase 2 — Widen strategy classes + full reputation math

**Goal.** Three classes with real proofs. Reputation is the full §8.2 formula.

### CX — Mean reversion circuit (WS1.B ✅ circuit + tests landed 2026-04-29)
- [x] `circuits/mean_reversion_v1.circom` — N-sigma deviation signal (in-circuit stddev via sum-of-squares; long on N-sigma down, short on N-sigma up, exit on mean re-cross or stop-loss). Public-input layout matches `momentum_v1` (14 PIs) so `StrategyVault.PI_*` and adapter `_PUBLIC_INPUT_COUNT = 14` are reused unchanged. **5 746 non-linear constraints — 29% of 20k budget.**
- [x] Unit tests: valid long on N-sigma down, valid short on N-sigma up, valid exit on mean re-cross, valid exit on stop-loss, plus 14 reject paths (insufficient deviation, wrong sign, params/oracle/trade-hash mismatches, exit-without-reason, …). **18 witness tests passing.**
- [x] Verifier adapter + on-chain registration — WS3.A landed 2026-04-29: `MeanReversionV1VerifierAdapter` (14 PIs, mirrors momentum). Real-proof fixture generator (`circuits/scripts/gen-fixture-mr.js`) + 4 Foundry round-trip tests including tampered-PI rejection. `DeployPhase2.s.sol` (WS3.B) re-points `TradeAttestationVerifier` at the adapter.

### CX — Yield rotation circuit (WS1.C ✅ circuit + tests landed 2026-04-29)
- [x] `circuits/yield_rotation_v1.circom` — Poseidon-Merkle inclusion of `(M_from, apy_from)` and `(M_to, apy_to)` against `yield_oracle_root` (depth 6 → 64 markets), Poseidon-Merkle inclusion of both market ids against a private `markets_allowlist_root` (depth 4 → 16 markets) bound through `trade_hash` so the on-chain side rejects any trade whose hash doesn't match `Poseidon(StrategyRegistry.marketAllowlistRoot(class), …public fields…)`. APY differential `apy_to − apy_from ≥ signal_threshold + bridging_cost`. 9 PIs (no params_hash slot — operator/registry params bind through trade_hash). **6 564 non-linear constraints — 44% of 15k budget.**
- [x] Unit tests: valid rotation, differential below threshold rejected, bridging cost erodes differential, M_from/M_to not in allowlist rejected, yield-root mismatch, apy claim diverges from oracle leaf, M_from == M_to rejected, amount_rotating = 0 rejected, trade-hash mismatch, tampered allowlist root. **11 witness tests passing.**
- [x] Verifier adapter + on-chain registration — WS3.A landed 2026-04-29: `YieldRotationV1VerifierAdapter` (9 PIs, distinct shape) + `StrategyVault.executeYieldRotationWithProof` class-aware entry path (PI_YR_* layout, `YieldRotationAttested` event). 9 vault tests + 4 adapter tests. Real-proof fixture generator (`circuits/scripts/gen-fixture-yr.js`).

### CX — Circuit budget gate (WS1.B/C support)
- [x] `circuits/scripts/check_constraints.sh` + `make check-constraints` target. CI gate fails if any compiled circuit exceeds 90% of its declared `BUDGET_*`. Current: momentum 28%, mean_reversion 29%, yield_rotation 44%.

### SX — Reference strategies for the new classes (WS2.B landed 2026-04-30)
- [x] `reference-strategies/mean_reversion_v1/` — Python impl on SDK. **`MeanReversionStrategy` (16-bar μ/σ z-score, n_sigma_x100 entry, mean re-cross + stop-loss exits), runtime with bar+NAV cadences, witness builder mirroring `gen-fixture-mr.js` (14 PIs, `executeWithProof` path), FastAPI shell on port 8006. 33 pytest cases passing. VPS deploy is Phase 6 deploy-hardening.**
- [x] `reference-strategies/yield_rotation_v1/` — scans allowlisted lending markets. **`YieldRotationStrategy` with `on_yield_tick` extension hook (base `on_bar` overridden to no-op since YR fires on yield cadence, not price bars). Python Poseidon-Merkle witness builder (yield depth 6, allowlist depth 4) producing 9-PI `executeYieldRotationWithProof` payloads with empty `Call[]` (Phase 2 = Kite-local-only; real cross-chain rotation lands Phase 5 with LayerZero). Reuses `oracle.poseidon` via `helios-oracle` workspace dep — Phase 3 will lift into shared `helios-poseidon` package. Vector-parity test (`test_merkle.py`) reproduces `gen-fixture-yr.js` yield root + trade_hash bit-exact, locking Python Poseidon ↔ circomlibjs for tree-shaped data. FastAPI shell on port 8007. 32 pytest cases passing.**
- [x] Prover service registers `mean_reversion_v1` + `yield_rotation_v1` classes (`services/prover/src/index.js` `REGISTERED_CLASSES` bumped). 5 prover tests still pass.
- [x] Oracle yield endpoints landed: `/v1/yield/recent`, `/v1/yield/markets`, `/v1/yield/root` + `YieldPoller` driving `YieldStore` with Aave/Compound stub feeders. 2 new endpoint tests.
- [x] Both registered on `StrategyRegistry` with real stake. **`contracts/script/RegisterPhase2Strategies.s.sol` deploys a SECOND `StrategyVault` per class with distinct non-zero `paramsHash` (different `signal_threshold`/`n_sigma`/`bridging_cost` per variant) and registers via `StrategyRegistry.registerStrategy(_, CLASS_*, 5000e6)`. 5 Foundry tests assert `strategiesByClass(C).length == 2`, both active, paramsHash distinct cross-class, stake pulled from operator, deployments JSON merge preserves Phase-1 entries. Cohort math (§8.2 `min_cohort_size = 2`) now satisfied.**
- [ ] Deploy `RegisterPhase2Strategies.s.sol` against Kite testnet — gated on WS6 e2e dependency landing; runs once and wires `strategyVault<Class>Variant2` keys into `deployments/kite-testnet.json`.

### SX — Full reputation formula (WS2.A engine ✅ landed 2026-04-29)
- [x] `PerformanceScore` — 0.5×7d + 0.3×30d + 0.2×90d normalized Sharpe; cohort-relative (median/IQR per class). **Engine groups `StrategyState`s by `declaredClass`, builds per-window cohort stats in `services/reputation/src/reputation/cohort.py`, normalizes each strategy's Sharpe via `(Sharpe − median) / IQR`. Spec deviation: NAV-delta proxy used in place of realized-trade-P&L Sharpe pending per-trade P&L emission from the strategy vault — documented in `score.py` module docstring.**
- [x] `RiskScore` — `1 - clip(MaxDD90d / 5000, 0, 1)`. **Engine derives 90d max drawdown from `NAVSnapshot` events directly; no schema bump (honors `project_subgraph_goldsky_wasm`).**
- [x] `ProofScore` — `ValidProofs / TotalProofAttempts`. **Computed against the 30d window of subgraph `Trade` events. Subgraph only emits on-chain (proof-valid) trades, so the ratio is binary 0/1 in Phase 2 — limitation noted; lifts when the prover service publishes attempted-but-rejected proofs.**
- [x] `StakeScore` — `log(1 + stake/1000) / log(1 + max_stake_in_class/1000)`. **Implemented; max_stake_in_class derived per tick from the active strategy set.**
- [x] `AgeScore` — `clip(sqrt(trades_attested / 1000), 0, 1)`.
- [x] Weights w_perf=0.40, w_risk=0.25, w_proof=0.15, w_stake=0.10, w_age=0.10. **Compile-time invariant via `assert` in `score.py`.**
- [x] Unit tests validate each component against `Helios.md §8.2` worked examples. **44 tests passing — `test_score_822.py` (component-by-component + aggregate), `test_cohort.py`, `test_windows.py`, `test_engine.py` (cohort divergence + drawdown extraction + componentsHash signing), `test_signer.py` (v1 + v2 typehash round-trip), `test_service.py` (REST + audit endpoint).**
- [x] `/audit` page exposes the inputs for every strategy's current score. **Backend: `GET /v1/audit/{actor}` returns five components, cohort stats per window, raw + normalized Sharpes, weights, and `componentsHash`. Frontend `/audit/[actor]/page.tsx` is WS5.**
- [x] **WS3.A typehash v2 + on-chain anchor upgrade — contracts side landed 2026-04-29.** `ReputationAnchorV2.sol` ships with EIP-712 domain version `"2"` and a typehash that binds `bytes32 componentsHash`. `IReputationAnchor.ReputationData` extended with `componentsHash`; new `ComponentsAnchored` event emits per update. Fresh deploy (V1 was non-upgradeable) via `DeployPhase2.s.sol` (WS3.B); existing registries' `immutable reputationAnchor` keeps V1 wired for delta propagation until Phase 5 redeploy. 6 V2 Foundry tests including tamper rejection. *Engine env flip to `REPUTATION_TYPEHASH_VERSION=2` happens once V2 address is wired in `services/reputation`.*
- [x] **WS3.B canonical Phase-2 deploy script landed 2026-04-30.** `contracts/script/DeployPhase2.s.sol` — single broadcast that (a) deploys real Groth16 verifiers + adapters for all three classes and re-points `TradeAttestationVerifier` per-class, (b) deploys `ReputationAnchorV2` and wires it to the existing registries, (c) deploys `OraclePriceAnchor` + `OracleYieldAnchor` (unblocks `services/oracle` auto-promote from dry-run), (d) optionally calls `StrategyRegistry.setMarketAllowlistRoot(CLASS_YR, root)` when `YR_MARKET_ALLOWLIST_ROOT` is set, (e) merges every new address into `deployments/<chain>.json` while preserving Phase-1 entries (bumps `phase` → "2", stamps `phase2DeployedAt`). Parameterized `runWith(Inputs)` entry point for tests; 6 Foundry tests covering rotation, anchor wiring, allowlist root (set + skipped), oracle-signer separation, and deployments-JSON merge. Replaces the WS3.A interim `DeployPhase2Upgrade.s.sol` stub.

### SX — Oracle hardening (WS1.A ✅ landed 2026-04-29 — commit `bfc55fb`)
- [x] Yield oracle signs APY snapshots per lending market (Aave, Compound stubs for now — real integrations in Phase 5). **`services/oracle/src/oracle/yield_state.py` + `sources/yield_{base,aave_stub,compound_stub}.py`. Uses the existing `LocalSigner.sign_quote` shape (asset slot ↦ market_id, price slot ↦ apy_bps_e6) so the on-chain anchor recovery flow stays single-codepath. `OracleYieldAnchor.sol` mirrors `OraclePriceAnchor` with a distinct EIP-712 type-hash to block cross-domain replay.**
- [x] Price oracle Poseidon-root anchored on-chain via a periodic commit. **`OraclePriceAnchor.sol` (append-only EIP-712 ledger, monotonic windows, replay nonce) + `oracle.anchor.PriceAnchorScheduler` (commits every `ORACLE_ANCHOR_INTERVAL_BARS` bars, default 50) wired into `Poller.on_snapshot`. Python signing parity locked by 7 anchor unit tests; on-chain side covered by 16 Foundry tests; vector parity with the momentum circuit's chained Poseidon locked by 10 `test_poseidon_chain.py` cases (canonical `momentum_v1.test.js` `buildValidInput` fixture). `chain_root` is now a BN254 field element (decimal string + bytes32 hex on the HTTP endpoint).**
- [x] Scenario mode supports scripted yield differentials for yield-rotation demos. **Aave/Compound stub feeders advance through deterministic APY tick sequences; the canonical scenario crosses Compound USDC above Aave USDC by tick 5 (≥1.0% spread) so `yield_rotation_v1` has a real differential to chase in CI.**

### SX — Strategy SDK v0.1 (WS4.A landed 2026-04-30)
- [x] `pip install helios-strategy-sdk` works from a test-PyPI mirror. **`.github/workflows/publish-sdk-testpypi.yml` builds + publishes on `sdk-v*` tag (and `workflow_dispatch`) via PyPI trusted publishing (OIDC). Tag/version drift gate fails the run if `sdk-v<x>` doesn't match `pyproject.toml`.**
- [x] `StrategyAgent` base class with `declared_class`, `asset_universe`, `max_position_size_usd`, `fee_rate_bps`, `on_bar`, `size_trade`, `should_exit`. **`packages/strategy-sdk/src/helios/agent.py` formalized: `on_bar` abstract, `size_trade`/`should_exit` non-abstract with safe defaults (clamp to `max_position_size_usd` ∧ `available_capital`; default `should_exit=False`). Internal `_set_capital` / `_set_position` hooks land for backtest + runtime. 7 unit tests cover declared-class enforcement, sizing clamps, and manifest pass-through.**
- [x] Backtest harness: `packages/strategy-sdk/src/helios/backtest.py` ships `run_backtest(strategy, prices, …)` returning a `BacktestReport` with NAV series, fills, Sharpe, max-DD, win rate, realized P&L. Pure-Python (no numpy); `helios.nav.NAVTracker` provides O(1) drawdown + Sharpe matching `services/reputation/windows.py` annualisation. CLI integration is WS4.B.
- [x] Local simulator: `synthesize_random_walk(assets, bars, seed)` (deterministic LCG + Box-Muller-lite) feeds `run_backtest` for CI smoke tests; 25 SDK pytest cases cover engine, NAV math, and synth determinism. CLI surface (`helios simulate`) is WS4.B.

### SX — CLI subcommands (WS4.B landed 2026-05-01)
- [x] `helios backtest --strategy ./my.py --period 90d` — wires WS4.A `run_backtest` + `synthesize_random_walk`; writes markdown report (NAV ASCII chart + full `BacktestReport` fields) to `docs/backtests/<class>/<name>_<period>.md`. Periods: `7d / 30d / 90d / 180d` at 1-hour bar cadence.
- [x] `helios simulate --strategy ./my.py --minutes 60` — deterministic 1-min mocked-market loop; per-10-bar status prints; finishes <1 sec; CI-usable.
- [x] `helios deploy --strategy ./my.py --vps user@host` — renders `templates/Dockerfile.strategy` (shipped in-package) + scp/ssh bootstrap (`docker build` + `docker run --restart unless-stopped`). Defaults to dry-run; `--execute` to apply. Optional `--requirements` for extra Python deps.
- [x] `helios stake top-up|initiate-withdrawal|claim-withdrawal --strategy-id <addr> --amount N` — auto-loads `StrategyRegistry`/`USDC` from `contracts/deployments/<chain>.json`; top-up issues two txs (`USDC.approve` + `topUpStake`); honors `KITE_RPC_URL` / `OPERATOR_PK` env; `--dry-run` for plan-only.
- [x] `helios test-proof --trade <spec.json>` — POSTs `{strategyClass, witnessInputs}` to `PROVER_URL/prove`; packs snarkjs proof into 256-byte `uint256[8]` form (matches `runtime._proof_to_bytes`); read-calls `TradeAttestationVerifier.verify(declaredClass, proof, publicInputs)`. `--skip-onchain` for CI.
- [x] Helpers: `_loader` (one-strategy-per-file enforcement), `_deployments` (env-overridable address lookup), `_proof` (snarkjs encoder + `bytes32` class IDs), `_chain` (`StakeClient` + `VerifierReader`).
- [x] Tests: 28 pytest cases under `packages/helios-cli/tests/` (loader, deployments, proof encoder, all five subcommands via `typer.testing.CliRunner` with monkeypatched httpx + chain clients). Pyright + ruff clean.
- [x] Docs: `docs/operator-guide.md` — install → write strategy → backtest → simulate → test-proof → deploy → stake → reputation, plus a troubleshooting matrix.

### CX/SX — Spec hardening (WS7) — added 2026-04-29 from spec review

Closes four soundness/framing gaps the reviewer flagged in `Helios.md` (ZK threshold binding, NAV signer ambiguity + auto-defund griefing, reputation cold-start, stake-weighting framing). See `docs/phase2-plan.md` WS7 for the detailed plan.

**WS7.A — ZK params commitment binding (CX)**
- [x] `StrategyRegistry.rotateParams` two-phase API landed 2026-04-29: `commitInitialParamsHash` (one-shot) + `initiateParamsRotation` (cooldown reuses `stakeCooldown`) + `completeParamsRotation` + `ParamsHashCommitted` / `ParamsRotationInitiated` / `ParamsRotated` events. 10 new Foundry tests.
- [x] `manifest.paramsHash` is now superseded at trade-time: `StrategyVault._activeParamsHash()` prefers the registry-committed value and falls back to the manifest only when zero (Phase-1 compat). Vault test `test_ExecuteWithProof_UsesRegistryParamsHashWhenCommitted` proves rotation is the only mutation path.
- [ ] `yield_rotation_v1`: full on-chain `trade_hash` reconstruction against `StrategyRegistry.paramsHashOf` requires Poseidon-on-Solidity (not in repo). WS7.A ships the YR-class entry path with class/allocator/window/dedupe checks + verifier dispatch; trade-hash reconstruction is documented as a `TODO(WS7.A)` in `StrategyVault.executeYieldRotationWithProof` and tracked for Phase 5/6.
- [ ] Update `Helios.md §9.3` PI list — done as part of this workstream
- [ ] Reputation engine: on `ParamsRotated`, reset `AgeScore` and the `PerformanceScore` window to the new params epoch (clean break in track record)
- [ ] `/strategies/[id]` and `/audit/[strategy]` surface the `paramsHash` rotation history (Phase 4 frontend; spec/event in Phase 2)
- [x] WS3.A also landed: `StrategyRegistry.setMarketAllowlistRoot(class, root)` (owner-gated) — canonical root for `yield_rotation_v1` allowlist proofs. (Circuit currently treats the root as a private witness, so on-chain enforcement of "operator used the canonical root" requires promoting it to a public input — documented as a v2 circuit change.)

**WS7.B — Reputation cold-start mechanism (SX)**
- [x] Engine: cohort-size fallback in `services/reputation/src/reputation/cohort.py` already at `min_cohort_size = 2` per WS2.A — bump to `min_cohort_size = 3` and add the explicit raw-Sharpe fallback documented in `Helios.md §8.7`
- [x] Engine: stake-only score floor when `trades_attested == 0` → `score = w_stake × StakeScore`; unit test
- [x] Sentinel: `bootstrap_share_bps` field on the meta-strategy schema (default 1000 = 10%); allocator reserves that share for strategies with `trades_attested < min_attested_trades` (default 50), allocated stake-weighted with flat performance prior
- [x] Sentinel unit + scenario tests: cold-start strategy receives bootstrap allocation even when the user's main filter (e.g., Sharpe ≥ 1.5) excludes it
- [x] `docs/reputation-math.md` documents the three cold-start components

**WS7.C — Auto-defund griefing + NAV signer (CX/SX, spec only in Phase 2)**
- [x] `Helios.md §6.3 / §6.4` updated — done as part of this workstream
- [x] Add fields to `MetaStrategy` schema in `UserVault`: `defundTwapBars` (default 3), `defundBondBps` (default 50), `defundConfirmBlocks` (default 25); update tests (round-trip + zero→default; UserVault.t.sol `test_SetMetaStrategy_RoundTripsDefundFields` + `test_SetMetaStrategy_AppliesDefundDefaultsWhenZero`)
- [ ] Add `defundRewardCapUsd` (default 500_000_000 = $500 USDC, 6 decimals) to `MetaStrategy` schema in `UserVault` — pairs with the bond-reward implementation below (added 2026-05-05 — Helios.md §6.3 numerical pinning)
- [x] Frontend `/onboard` Advanced disclosure surfaces the three defaults read-only (`CustomizationPanel.tsx::DefundDefaults`); tuning controls + bond UX deferred to Phase 4
- [ ] **Implementation deferred to Phase 4** — TWAP/bond/confirm-window logic in `AllocatorVault.defundStrategy`; Phase 2 only commits the spec shape and meta-strategy fields so existing scenarios still pass. **Phase 4 must enforce these constants from `Helios.md §6.3`:** bond reward = 50 bps of defunded notional, capped at `defundRewardCapUsd` ($500 default); reward paid from the strategy's stake (not user principal); `OraclePriceAnchor.freshness()` gates the trigger — if `secsSinceLastSnapshot > MAX_STALENESS_SEC` (180s) the defund path skips rather than false-fires (added 2026-05-05 — Helios.md §6.3 / §6.10 numerical pinning)
- [ ] **Phase 4 — NAV divergence slash path on `StrategyVault.reportNAV`** (new ticket, added 2026-05-05 — Helios.md §6.4 numerical pinning). Compare each `reportNAV` against the on-chain marked NAV (vault balance + `OraclePriceAnchor.twapBars()` priced asset universe). If `|signed - marked| / marked > NAV_DIVERGENCE_THRESHOLD_BPS` (default 500 = 5%) for two consecutive snapshots, emit `NavDivergenceObserved(strategy, signed, marked, snapshotNonce)` and queue the strategy for `slash` via `StrategyRegistry.slash` (Helios multi-sig executes in v1). Tests: round-trip divergence detection, single-snapshot below-threshold no-op, two-consecutive trigger, oracle-stale skip, marked-NAV computation against `OraclePriceAnchor`. Pairs with the `OraclePriceAnchor.freshness()` gate above so a stale oracle can't false-trigger divergence.
- [x] Phase 4 task tracker: bond UX checkbox added to Phase 4 §"FE — System polish"

**WS7.D — Stake-weighting honest framing (docs only)**
- [x] `Helios.md §8.1` principle 2 reframed as deliberate tradeoff — done
- [x] `Helios.md §8.5` adds stake-stripped sub-rank as v2 candidate — done
- [ ] `docs/reputation-math.md` mirrors the framing once the doc is written in Phase 6 (note in this checklist, not separately tracked)

### Acceptance for Phase 2
- [x] Multiple strategies of each class registered with non-zero capital — WS6 PR1 + `RegisterPhase2Strategies.s.sol` + PR3.5.C register 7 vaults across 3 classes (2 per class + 1 cold-start fresh momentum); 5 Foundry tests assert `strategiesByClass(C).length ≥ 2` and stake pulled from operator
- [x] Reputation scores visibly diverge based on realized performance + drawdown — WS6 PR3.B drives the §8.2 engine over 90d compressed time; `scripts/e2e_scenario_phase2.py:1198` asserts `primary.outputs.score_e4 > variant2.outputs.score_e4` for every class
- [x] Backtest reports for each reference strategy committed under `docs/backtests/<class>_90d.md` — `36fa0cf` (5 seeds per class; YR uses a stand-alone `on_yield_tick` harness pending Phase 3 SDK support)
- [x] External contributor could, in principle, publish a new momentum strategy using only the SDK + public docs — PR5.A (`d0058af`) shipped the Dockerfile + smoke + fixtures; PR5.B (`aebc61b`) added `release-wheels.yml` to attach the four wheels to a GitHub Release on every `sdk-v*` tag and renamed the CLI dist to `helios-trader-cli` (the bare `helios-cli` PyPI name is squatted by an unrelated LLM-usage tracker). `sdk-v0.1.0` cut + verified end-to-end: `helios-strategy-sdk` published to test-PyPI, all four wheels attached to `https://github.com/emark-cloud/helios/releases/tag/sdk-v0.1.0`, `INSTALL_MODE=release` smoke green against the real release URL — pip's "Successfully installed" line contains the four expected `helios-*` packages with no squatter swap.
- [x] WS7.A: a `ParamsRotated` event is emitted in the e2e scenario; reputation engine resets `AgeScore` on the new params epoch — WS6 PR3.5.A + PR3.5.B; `scripts/e2e_scenario_phase2.py:813-1117` runs `initiateParamsRotation` → `evm_increaseTime(7d)` → `completeParamsRotation` → re-tick the engine and asserts the reset
- [x] WS7.B: e2e scenario includes a brand-new strategy with zero trade history that receives a bootstrap allocation through Sentinel (`services/sentinel/tests/test_loop.py::test_cold_start_strategy_receives_bootstrap_allocation`)
- [x] WS7.C: meta-strategy schema carries the three defund fields; UserVault tests assert round-trip + default-on-zero; AllocatorVault test fixtures construct the new fields even though enforcement is deferred to Phase 4

---

## Phase 3 — AllocatorSDK + Helix ✅ (done 2026-05-06)

**Goal.** Marketplace mechanism is real. Two allocators on-chain, users can pick.

Implementation plan: `docs/phase3-plan.md` (17-step PR sequence, PRs #36–#54, all merged).

### SX — Allocator SDK
- [x] `packages/allocator-sdk` with `BaseAllocator`, `rank_strategies`, `allocate` abstract methods (Phase 0/1 scaffolding; lifted out of `services/sentinel` in WS1.A — PRs #36/#37/#38)
- [x] Helpers: `default_top_k_allocation`, `score_weighted_allocation`, `pairwise_correlation_from_goldsky`, `btc_realized_vol_30d`, `detect_regime` (WS1.B — PR #39)
- [x] SDK handles: onboarding, drawdown monitoring at 60s, fee crystallization, defund/rebalance tx submission via Passport sessions, Goldsky integration, ReputationAnchor integration for allocator reputation, WS event emission, stake management, Docker packaging, local backtest (WS1.A — PRs #36/#37/#38; backtest harness WS1.C — PR #48)
- [x] CLI: `helios-allocator init | backtest | simulate | stake | deploy | logs` (WS2.A — PR #47; WS2.B — PR #49)
- [x] **`packages/allocator-sdk/README.md` "Build with Claude Code" section** (WS2.A — PR #47). 5-line scaffold prompt + pointer to `CLAUDE.md`; scaffold output (`helios-allocator init`) is the AI-native entry path.

### SX — Helix-lite (second reference allocator)
- [x] `services/helix/` built **entirely on top of allocator-sdk** (WS3.A — PR #42)
- [x] `helix_fee_factor` — fixed-weight fee penalty (WS1.B — PR #39; regime-adaptive variant deferred per `docs/phase3-plan.md` scope cuts)
- [x] `helix_greedy_pick` — top-K greedy selection by reputation × fee factor (WS1.B — PR #39; correlation-aware variant ships unwired in v1)
- [x] Registered on `AllocatorRegistry` with `isReferenceBrand = true`, name `"Helios Helix"`, fee rate 600 bps (WS3.B — PR #43)
- [x] Runs alongside Sentinel on the VPS (PM2 entry shipped in PR #42; VPS deploy itself is Phase 6)

### SX — Allocator reputation
- [x] Reputation Engine computes allocator scores from aggregate user net P&L above HWM, drawdown discipline (did they actually fire bad strategies on time?), user retention, stake (WS5.A — PR #40)
- [x] `postReputationUpdate` with `actor_type = ALLOCATOR` (WS5.A — PR #40)
- [x] Allocator leaderboards queryable via subgraph (WS5.B subgraph entities — PR #41; FE leaderboard — PR #46)

### SX — Strategy SDK hardening (carried over from Phase 2 backtest writeups)
- [x] **YR-aware backtest engine.** `helios.backtest.run_yield_backtest` lifts the bespoke harness into the SDK; `helios backtest --strategy …yield_rotation_v1/strategy.py` now routes through the YR driver. (WS4 PR 1/3 — PR #51). The standalone harness is now a thin wrapper around the SDK driver, kept because the reference impl needs constructor args.
- [x] **Position flipping in `_apply_intent`.** "Flip = exit + open" path lands the closing leg's realised P&L on `BacktestReport.realized_pnl` instead of silently netting opposing qtys. (WS4 PR 2/3 — PR #52)
- [x] **NAV-based / vol-target sizing helper.** `helios.sizing.nav_target_notional` + `TradeIntent.is_nav_targeted` flag + `StrategyAgent.size_trade(nav_target=True)`. Reference momentum + mean-rev opt in. Backtest writeups refreshed. (WS4 PR 3/3 — PR #53)
- [x] **Mirror remaining packages to test-PyPI.** All four publishable Helios packages are now live on test-PyPI at version `0.1.0`: [`helios-strategy-sdk`](https://test.pypi.org/project/helios-strategy-sdk/0.1.0/), [`helios-contracts-abi`](https://test.pypi.org/project/helios-contracts-abi/0.1.0/), [`helios-allocator-sdk`](https://test.pypi.org/project/helios-allocator-sdk/0.1.0/), [`helios-trader-cli`](https://test.pypi.org/project/helios-trader-cli/0.1.0/). `.github/workflows/publish-sdk-testpypi.yml` mirrors all four on every `sdk-v*` tag via OIDC trusted publishing (matrix per package, same `testpypi` environment). Trader-cli wheel build had to drop a redundant `force-include` in `packages/helios-cli/pyproject.toml` because test.pypi.org's 2026 ZIP validator rejects duplicate local-header entries (older PyPI silently accepted the same wheel — `release-wheels.yml` artefacts on the existing `sdk-v0.1.0` GitHub Release have the duplicates but pip still installs them, so they're left as-is until the next tag rebuilds them). GitHub Releases remains the canonical wheel host for the external-contributor flow.
- [x] **`helios scaffold-strategy <class>` CLI** (WS2.C — PR #50). Per-class templates for `momentum_v1`, `mean_reversion_v1`, `yield_rotation_v1`. Each scaffold installs from public PyPI with no workspace runtime deps and is runnable through `helios backtest` immediately.
- [x] **`packages/strategy-sdk/README.md` "Build with Claude Code" section** (WS2.C — PR #50).

### FE — Allocator surface
- [x] `/allocators` directory: Sentinel first with "Official Reference" badge, Helix second (same badge), space for third parties below (WS6.A — PR #44)
- [x] Each card: name, fee rate, supported classes, ranking function one-sentence + "view code" link, current users, total capital managed, reputation, stake (WS6.A — PR #44)
- [x] `/onboard` adds an allocator-picker step (WS6.B — PR #45)
- [x] `/allocators/[name]` detail page (WS6.A — PR #44)
- [x] Allocator leaderboard on `/dashboard` (WS6.C — PR #46)

### SX — Phase 3 acceptance e2e (WS7 — PR #54)
- [x] `scenarios/phase3-divergence.py` — drives Sentinel + Helix in-process, asserts the four acceptance flows (capital flow per allocator, divergence ≥5% on shared strategies or set-difference, drawdown defund within one tick, HWM × 1.05 fee settle within one tick)
- [x] `scripts/e2e-phase3.sh` — wrapper invoked locally and by the GH Action
- [x] `.github/workflows/phase3-e2e.yml` — runs on every PR touching the allocator/sentinel/helix/reputation/subgraph paths

### Acceptance for Phase 3
- [x] A user picks Sentinel at onboarding → flow works. Same user re-onboards picking Helix → flow works with different allocation decisions visible. (WS6.B onboarding flow — PR #45; in-process divergence assertion — PR #54)
- [x] `helios-allocator init --name "TestThirdParty"` scaffolds a working allocator that can be registered on Kite testnet without any modifications to Helios code. (WS2.A scaffold + install acceptance test — PR #47; on-chain register-on-anvil gate deferred to a follow-up that lands alongside `DeployPhase3` on a refreshed testnet pin)
- [x] Allocator leaderboard on dashboard shows both Sentinel and Helix with diverging reputation as their decisions play out differently across users. (WS5.A engine — PR #40; WS5.B subgraph — PR #41; WS6.C leaderboard — PR #46; divergence scenario — PR #54)

---

## Phase 4 — Frontend completion + signature interactions

**Goal.** Every DESIGN.md surface implemented. Signature moments land.

### FE — Remaining pages
- [ ] `/` landing — confident headline, live stats band from subgraph (total capital managed, active strategies, attested trades, active allocators), two primary CTAs, secondary links. No feature sections, no testimonials, no FAQ.
- [ ] `/strategies/[id]` — manifest header, reputation breakdown panel (perf/risk/proof/stake/age), P&L curve with drawdown envelope, recent trades table with shield icons, current allocators, NAV timeline
- [ ] `/audit/[strategy]` — every trade paginated, proof hash + verification result, "verify this proof yourself" modal, reputation-calculation inputs exposed, JSON dump link. Celebrated ZK treatment per `DESIGN.md §12`.
- [ ] `/judge` — video link, "Try the demo scenario" button, contract addresses with explorer links, GitHub links, `verify-trade.js` command block, 5-step eval checklist, live transaction counts. **Self-sufficient even without VPS up** (added 2026-05-05 — judging-criteria audit, criterion C real-world applicability): expose Kite testnet RPC URL, all deployed addresses (auto-read from `contracts/deployments/kite-testnet.json`), Goldsky endpoint, and Kitescan deeplinks for a recent scenario's `TradeAttested` / `Reallocated` / `AutoDefunded` events so judges can verify the system end-to-end before VPS deploys in Phase 6.
- [ ] `/docs` route deferred — `/judge` instead links out to operator + allocator guides on GitHub (see Deferred §)

### FE — Sunburst viz (v1, simplified)
- [ ] Concentric-ring viz: user → allocator → strategies (skip positions ring for v1)
- [ ] Implementation: hand-rolled SVG or Recharts `Pie` with two layers — bespoke d3 + ticked-motion physics deferred to v2 polish (see Deferred §)
- [ ] Segments sized by capital weight, colored by chain
- [ ] Amber selected state
- [ ] Hover reveals strategy name + allocated + NAV + P&L
- [ ] Click navigates to strategy detail
- [ ] Mini-sunburst variant for allocator cards

### FE — Signature interactions
- [ ] Cascade — staggered 80–120ms stages across sunburst + table + activity rail
- [ ] Auto-defund — row red-border, NAV ticks to zero over 2s, sunburst rebalances, replacement row appears, activity rail prints both events. Total ~5–6s. Thermostat-kicking-on feel.
- [ ] Cross-chain rep update — chain badge pulse, in-flight indicator, resolve on arrival (don't hide LayerZero latency)

### FE — System polish
- [ ] Auto-defund bond UX on `/dashboard` (WS7.C Phase 4 portion). Surface "defund pending confirmation" state in the activity rail, expose `defundTwapBars` / `defundBondBps` / `defundConfirmBlocks` controls in onboard (currently read-only in `CustomizationPanel.tsx::DefundDefaults`), and walk the trigger caller through posting + reclaiming the bond. Pairs with `AllocatorVault.defundStrategy` enforcement landing the same phase.
- [ ] Keyboard navigation per `DESIGN.md §5.5`: `J/K`, `/`, `Esc`, `G D`, `G S`, `G A`, `?` shortcut menu
- [ ] Reduced-motion media query reduces every signature interaction to instant
- [ ] Focus rings visible and amber-toned
- [ ] WCAG AA contrast audit passes across all pages
- [ ] Projector legibility check (low-contrast crush test on 1080p)
- [ ] `/onboard` error UX — `OnboardClient.tsx:72-74` surfaces raw `Failed to fetch` when Sentinel is unreachable, hiding that the signature succeeded. Distinguish "signed but allocator unreachable" (retryable, signature kept) from "signing failed" (rejected/aborted). Surfaced during Tier 1 local-testing 2026-04-28.
- [ ] Sentinel observes on-chain events so the dashboard reflects Tier 3 cascades. Today `e2e_scenario.py` drives `AllocatorVault` directly and `services/sentinel` only emits events from its own decision loop, so the activity rail stays blank during scenario runs even though the chain trail is correct (`AllocationCreated`, `StrategyDefunded`, `NAVReported`). Wire a chain-watcher (Goldsky-against-anvil or direct `eth_getLogs` poller) so chain events become `SentinelEvent`s on the WS feed. Closes the local-testing.md Tier 3 caveat. Surfaced 2026-04-28.

### FE — Passport onboarding rebuild (added 2026-04-30 from `docs/kite-passport-integration.md`)

Replaces the Phase 1 EOA `personal_sign` stub flow with the real Kite Passport widget. Choice C from the integration proposal: Passport for onboarding/funding, AA SDK for execution, on-chain ACL cascade. **Migrates every `[PASSPORT-STUB]` tag in the frontend.**

- [ ] Add `@gokite-network/auth@0.1.16` and `gokite-aa-sdk@1.0.15` to `frontend/package.json` (pin exact)
- [ ] `.env.example` — replace `KITE_PASSPORT_SIGNER_PK` with `NEXT_PUBLIC_PARTICLE_PROJECT_ID`, `NEXT_PUBLIC_PARTICLE_CLIENT_KEY`, `NEXT_PUBLIC_PARTICLE_APP_ID`, `NEXT_PUBLIC_AA_ENTRYPOINT_ADDRESS`, `NEXT_PUBLIC_AA_FACTORY_ADDRESS` (from Kite docs)
- [ ] `frontend/src/app/onboard/OnboardClient.tsx` — replace MetaMask connect + `personal_sign` flow with `GokiteNetwork.login()` + `SmartAccount.getAddress()` per `docs/kite-passport-notes.md` Pattern 1
- [ ] Build the batched onboarding userOp: `USDC.approve(UserVault)` + `UserVault.deposit` + `setMetaStrategy` + `delegateToAllocator` — submitted as a single paymaster-sponsored userOp via `sdk.sendUserOperationAndWait`
- [ ] Drop the `signature` parameter from `UserVault.setMetaStrategy` if still present (AA wallet's userOp signature is verified at the EntryPoint level — no separate EIP-712 path needed). Confirm Phase 1 contracts already have this shape; if not, schedule a UUPS-upgrade alongside the onboarding flip.
- [ ] Migrate every `[PASSPORT-STUB]` comment tag — search the frontend for the marker, swap each to the new flow, drop the tag once verified
- [ ] Re-record the demo voiceover per `Helios.md §14.1` — passkey, no MetaMask popup
- [ ] Re-run `scripts/e2e-scenario.sh` and confirm the Phase 1 vertical-slice acceptance criteria still pass against the new flow

### Acceptance for Phase 4
- [ ] All surfaces from `DESIGN.md §9` live
- [ ] Scenario mode from Phase 1 replays at full visual fidelity — cascade animates staggered, auto-defund lands as thermostat moment, activity rail prints both events in sync
- [ ] An external designer reviewing the live app says "Bloomberg meets Vercel v0," not "DeFi app"
- [ ] Passport onboarding rebuild merged: zero `[PASSPORT-STUB]` tags remain in frontend; `/onboard` is one passkey approval; e2e scenario green

---

## Phase 5 — Cross-chain

**Goal.** Strategies trade where liquidity is best. Reputation still canonical on Kite.

### CX — Base + Arbitrum contracts
- [ ] `StrategyVault`, `TradeAttestationVerifier`, per-class verifiers, `HeliosOApp` deployed on Base Sepolia
- [ ] Same set deployed on Arbitrum Sepolia
- [ ] Per-chain verifier contracts registered for all three classes
- [ ] Deploy scripts + `deployments/base-sepolia.json` + `deployments/arbitrum-sepolia.json` populated

### CX — LayerZero OApp
- [ ] `HeliosOApp` on all three chains wired to LayerZero V2 endpoints
- [ ] `sendReputationUpdate(dstEid, strategy, data, options)` on Base/Arbitrum → `_lzReceive` on Kite → `ReputationAnchor.postCrossChainUpdate`
- [ ] Replay protection via nonce + per-strategy sequence numbers
- [ ] Mock USDC OFT deployed on all three testnets for capital bridging in the demo

### SX — Cross-chain strategy deployments
- [ ] Momentum strategy on Base trades ETH/USDC, WBTC/USDC, SOL/USDC on Uniswap V4 (V3 if V4 integration blocked)
- [ ] Yield-rotation strategy on Arbitrum moves capital Aave V3 ↔ Compound V3
- [ ] Strategies emit NAV + trade attestations locally; HeliosOApp batches and forwards to Kite
- [ ] Subgraph indexes events across all three chains; mapping merges into canonical `Strategy` entity

### FE — Cross-chain UI
- [ ] Chain badges on every strategy row
- [ ] Cross-chain reputation-in-flight indicator per `DESIGN.md §10.3`
- [ ] `/strategies` filterable by chain
- [ ] Sunburst segments chain-colored

### Acceptance for Phase 5
- [ ] Phase 1 scenario extended: one strategy per chain gets allocated, all execute real trades with real proofs on their local chain, reputation propagates back to Kite.
- [ ] A profitable trade on Arbitrum → ~30–60s later → Kite reputation ticks up → dashboard renders the in-flight → resolved visual
- [ ] Cross-chain reputation has a measurable effect on Sentinel/Helix allocation decisions

---

## Phase 6 — Audit surface, polish, security hardening

**Goal.** Judge-ready, defensible under scrutiny. Includes promotion to Kite mainnet per `docs/deployment-strategy.md` (hybrid testnet→mainnet).

### Mainnet promotion (decided 2026-04-25)
- [ ] Confirm hackathon allows mainnet submission + Passport is live on mainnet (gating questions)
- [ ] Acquire KITE for deploys + demo capital (~$100–500 demo float)
- [ ] Slither / Mythril **clean** on every Phase 1 contract before any mainnet tx (Echidna deferred — see Deferred §)
- [ ] `contracts/script/DeployMainnet.s.sol`; populate `contracts/deployments/kite-mainnet.json`
- [ ] Swap `MockSwapRouter` calls for real Algebra Integral router on mainnet
- [ ] Swap `oracle/sources/binance.py` for `oracle/sources/algebra.py` (TWAP from real pools)
- [ ] Mainnet subgraph deployed alongside testnet (separate Goldsky version)
- [ ] Frontend chain switcher (testnet = staging, mainnet = demo)
- [ ] `/judge` page links to live mainnet contracts + the deployment-strategy doc

### FE — Judge + audit surfaces
- [ ] `/judge` complete per `DESIGN.md §9.8` — press-kit styling, no marketing copy
- [ ] `/audit/[strategy]` complete per `DESIGN.md §9.7` — forensic, document-like, celebrated ZK treatment
- [ ] Live transaction counts pulled from subgraph on every render
- [ ] `scripts/verify-trade.js` — standalone Groth16 re-verification, copy-pasteable command from `/judge`

### CX — Security passes
- [ ] Slither run clean (or all findings triaged + documented)
- [ ] Mythril run clean
- [ ] Circuit unit tests for every class cover: zero inputs, max inputs, boundary conditions, every invariant branch
- [ ] Internal threat model walkthrough against `Helios.md §15.2` — every row has a test or a documented mitigation

### OP — Deploy hardening
- [ ] PM2 ecosystem file for all services with auto-restart, log rotation
- [ ] Nginx reverse proxy with rate limiting on public endpoints — **set explicit per-route values** (added 2026-05-05 — judging-criteria audit, criterion A "scoped keys, rate limits"). Read endpoints (e.g. `/v1/strategies`, `/v1/allocators`, `/v1/scores`): 100 req/min per IP. Write endpoints (e.g. `/v1/onboard`, allocator command surfaces): 10 req/min per IP. Document the values in `deploy/README.md` so judges can see the rate-limit story without reading nginx config.
- [ ] Health-check endpoints monitored; alerting via PM2 logs + email digest (Telegram admin channel deferred with the bot — see Deferred §)
- [ ] Postgres backups + restore runbook
- [ ] Secrets in VPS env only, never committed
- [ ] **VPS pre-deploy ≥ 48h before judging deadline** (added 2026-05-05 — judging-criteria audit, criterion C). Calendar move only — no code change. Ensures `helios.market` (or chosen subdomain) is reachable with valid TLS during evaluation. Falls back to `/judge`'s self-sufficient artifacts list if anything goes wrong day-of.

### Docs
- [x] `docs/operator-guide.md` — how to ship a strategy (landed 2026-05-01 with WS4.B)
- [ ] `docs/allocator-guide.md` — how to ship a competing allocator
- [ ] `docs/reputation-math.md` — the §8 formula, annotated + worked examples
- [ ] `docs/circuit-specs.md` — Circom circuit invariants per class
- [ ] `docs/threat-model.md` — §15 rendered as a standalone doc
- [ ] `docs/audit-checklist.md` — for external auditors
- [ ] Backtest reports at `docs/backtests/` for every reference strategy
- [ ] `README.md` — judge-friendly entry, links to demo video, live URL, /judge page, repo map. **Includes a "Reproduce the demo in 5 minutes" block at the top** (added 2026-05-05 — judging-criteria audit, success-slide row 7) with the canonical sequence (`pnpm install && uv sync && forge install && pnpm dev`, then `scripts/e2e-scenario.sh`), and a **"Rate limits & scoped permissions" subsection** (criterion A) listing concrete values: per-strategy capital cap (Solidity ACL in `UserVault`), per-route Nginx limits, strategy-agent self-throttle (`min_bar_interval` in `strategy-sdk`).

### Demo
- [ ] 3-minute live demo script rehearsed end-to-end
- [ ] 90-second backup video recorded and hosted
- [ ] Demo setup runbook: which services to start, which scenario to load, which browser window to open first
- [ ] Cold-start verification: fresh VPS + git clone + `docker-compose up` + env file → Phase 1 scenario passes within 10 minutes

### Acceptance for Phase 6
- [ ] A cold judge following `/judge`'s 5-step checklist completes evaluation in under 5 minutes
- [ ] Judge can verify a ZK proof independently against an on-chain tx and confirm it matches
- [ ] Slither/Mythril all pass (or every finding documented + justified)
- [ ] Cold-start demo succeeds on a machine that has never touched the repo before
- [ ] Backup video is uploaded and linked

---

## Cross-cutting gates (apply to every phase after the one that introduces them)

- [ ] Foundry coverage ≥ 85% on all contracts at all times from Phase 1
- [ ] Every strategy class has: circuit + unit tests + Python reference + backtest report + subgraph entity + frontend filter
- [ ] End-to-end scenario runs in CI on every PR from Phase 1 onward
- [ ] ABI changes trigger `packages/contracts-abi/` regeneration + downstream build check
- [ ] No `any` in TypeScript; no unformatted Solidity; no unlinted Python
- [ ] `DESIGN.md §4.3` amber budget respected (2–5% of pixels)
- [ ] `DESIGN.md §13` motion budget respected (smooth motion only in the listed exceptions)

---

## Deferred (post-hackathon)

Cuts taken 2026-05-05 to deliver a working demo faster and let the operator (emark) use the app end-to-end without service-side detours. Each item lands in `Helios.md §17` (post-hackathon roadmap) so the trajectory stays explicit.

- **Telegram bot (`services/bot/`, `@helios_market_bot`).** The 0:50–1:30 and 1:30–2:10 demo beats are carried by the dashboard activity rail (`/dashboard` already streams `SentinelEvent`s over WS). Restoring the bot revives `services/bot/`, the token provisioning flow, the DESIGN.md §15 message templates as bot output, and the `/dashboard` opt-in step. Roadmap: post-hackathon Phase 1 (Months 1–3).
- **x402 paid services (Choice G).** Pieverse facilitator + per-service pricing curves + `X-Payment` middleware across prover/oracle/reputation. Strong agent-economy demo polish but not in the headline 3-min script. Roadmap: post-hackathon Phase 1.
- **Helix regime-adaptive fee + correlation-aware greedy.** AllocatorSDK still exposes the hooks (`pairwise_correlation_from_goldsky`, `btc_realized_vol_30d`, `detect_regime`) so any third party can build a correlation/regime allocator from day one — Helix v1 just doesn't use them. Helix-lite still produces visibly different allocations from Sentinel via fee weighting + greedy pick over reputation. Roadmap: post-hackathon Phase 1.
- **`/allocators` side-by-side comparison mode (select 2+).** Per-allocator detail pages + the directory list cover the marketplace narrative; the side-by-side compare is polish.
- **Bespoke d3 sunburst with mechanical step animation.** Phase 4 ships a simpler concentric-ring viz (hand-rolled SVG / Recharts `Pie`). Bespoke d3 + ticked-motion physics on rebalance is v2 polish. Roadmap: post-hackathon Phase 1.
- **`/docs` embedded operator + allocator guides.** `/judge` links out to the markdown in `docs/` on GitHub instead. Embedded MDX rendering is post-hackathon.
- **Echidna property tests.** Slither + Mythril clean is the v1 security bar. Echidna for vault solvency / allocation bounds / drawdown-permissionless / reputation overflow is post-audit work. Roadmap: post-hackathon Phase 2 (Months 4–6).
- **Telegram admin alerting channel.** Replaced by PM2 logs + email digest in v1; revives with the bot.
