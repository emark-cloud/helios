# Helios — Phased Implementation Checklist

Mirrors the build plan at `/home/emark/.claude/plans/i-want-to-start-jiggly-hare.md`. Check items as they land. Each phase has an **Acceptance** section — do not declare a phase done until every acceptance criterion passes.

Tracks: **CX** (contracts/circuits), **SX** (services/SDKs), **FE** (frontend/bot), **OP** (infra/ops).

Current phase: **Phase 1** (Phase 0 complete except for items requiring user action — see below).

---

## Phase 0 — Bootstrap & ground truth ✅ (done 2026-04-25, modulo user-action items below)

**Goal.** Empty repo → working dev loops for every layer, frozen interface contracts, infra accounts ready.

### Outstanding (requires user action — does not block Phase 1 scaffolding)
- [x] Goldsky account + `GOLDSKY_API_KEY` provisioned; CLI pinned in `subgraph/package.json`, project "Helios" reachable. Full `pnpm --filter subgraph deploy` runs in Phase 1 once `subgraph.yaml` has datasources.
- [x] Vercel project `helios-frontend` linked to `emark-cloud/helios` (root `frontend/`, production = `main`); preview deploys auto-fire on PRs. `VERCEL_TOKEN` in `.env`. See `deploy/vercel-notes.md`.
- [x] VPS reservation — Servarica Montreal (8 GB / 2 dedicated cores / 250 GB NVMe, Ubuntu 24.04.4 LTS) at `helios@38.49.216.27`. Bootstrap complete: Docker 29.4 / Node 20.20 / PM2 5.4 / nginx 1.24 installed; helios user created with sudo+docker; UFW restricts to 22/80/443; 2 GB swap; sshd hardened to key-only auth (password auth blocked at protocol level). SSH key at `~/.ssh/helios_vps`. Deploy services via `pm2 start deploy/ecosystem.config.cjs` once Phase 1 services are ready.
- [ ] **BLOCKED (external)** — Kite Passport smoke test against live testnet. Public launch of Passport pending per Kite team announcement (2026-04-25); hackathon deadline extended ≥2 weeks. Phase 1 work proceeds with EOA-signature stubs at every Passport touchpoint (see `docs/kite-passport-notes.md` for the swap-in checklist).

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

### CX — Contracts
- [ ] `UserVault.sol` — MetaStrategy struct, `setMetaStrategy`, `deposit`, `delegateToAllocator(sessionTTL)`, `withdraw`, `settleAllocatorFee`. UUPS upgradeable.
- [ ] `AllocatorVault.sol` — AllocationRecord struct, `allocateToStrategy`, `defundStrategy` (permissionless when drawdown breached), `rebalance`, `settleStrategyFee`, `withdrawAllocatorFees`.
- [ ] `StrategyVault.sol` — StrategyManifest, `executeWithProof(proof, publicInputs, trades)`, `reportNAV`, `distributeRealized`, `withdrawToAllocator`, `slash`.
- [ ] `StrategyRegistry.sol` — `registerStrategy`, `topUpStake`, `withdrawStake` (7-day cooldown), `deactivate`, `updateReputation`, `slash`.
- [ ] `AllocatorRegistry.sol` — `registerAllocator`, reserved-name enforcement for `"Helios Sentinel"` + `"Helios Helix"`, `isReferenceBrand`, same stake/cooldown/slash pattern.
- [ ] `ReputationAnchor.sol` — `postReputationUpdate` (signer-gated), `postCrossChainUpdate` (OApp-gated, but OApp stub for now), `ActorType` enum.
- [ ] `TradeAttestationVerifier.sol` — registry of per-class verifier addresses, `verify(class, proof, publicInputs)`.
- [ ] Foundry tests per contract — happy paths, revert paths, out-of-bounds delegation, drawdown-breach permissionless defund, stake cooldown, reserved-name attempt → revert.
- [ ] Foundry coverage ≥ 85% across all Phase 1 contracts.
- [ ] Deploy script `contracts/script/DeployPhase1.s.sol` + recorded addresses in `deployments/kite-testnet.json`.

### CX — Momentum circuit
- [ ] `circuits/momentum_v1.circom` implements constraints per `Helios.md §9.3`:
  - [ ] `asset_in` / `asset_out` in manifest asset universe
  - [ ] `amount_in ≤ max_position_size`
  - [ ] `min_amount_out` respects max slippage (manifest-bounded)
  - [ ] `price_observations` Poseidon-hash to a committed oracle root
  - [ ] Direction-specific constraints (long entry: N-period return > threshold + flat/short precondition; short entry: symmetric; exit: signal-flip or stop-loss true)
  - [ ] `block_window_end - block_window_start ≤ 100`
- [ ] Constraint count ≤ 20k (target ~15k)
- [ ] Unit tests covering: valid long entry, valid short entry, valid exit, invalid (amount over cap), invalid (asset out of universe), invalid (threshold not exceeded), boundary (exact threshold)
- [ ] `MomentumV1Verifier.sol` generated via snarkjs, deployed on Kite testnet, registered in `TradeAttestationVerifier`
- [ ] Proof generation p95 ≤ 2s on commodity VPS

### SX — Prover Service
- [ ] `POST /prove` accepts `{ strategyClass, witnessInputs, publicInputs }`, returns `{ proof, publicSignals }`
- [ ] Loads `momentum_v1.wasm` + `momentum_v1.zkey` at startup; class-dispatched
- [ ] Degraded-mode behavior: if snarkjs crashes or takes >30s, respond 503; no silent fallback
- [ ] Integration test: strategy service → prover → on-chain verify round-trip

### SX — Strategy Service (momentum reference)
- [ ] Polls 1-minute bars for WKITE, USDC.e, WETH from a configured price source (Helios oracle for Phase 1)
- [ ] `on_bar(asset, snapshot)` implements momentum per `Helios.md §10.2`
- [ ] Constructs trade calldata for the Algebra Integral DEX router
- [ ] Calls prover, then `StrategyVault.executeWithProof`
- [ ] Reports NAV every 5 minutes
- [ ] Emits events consumed by subgraph
- [ ] Deploy to VPS via `deploy/services/strategy-momentum.Dockerfile`

### SX — Sentinel (reference allocator)
- [ ] Loop implements the six-step decision cycle from `Helios.md §11.2`
- [ ] Ranking function (`Helios.md §8.3`): `ReputationScore × CapacityFactor × FeeFactor × ClassFitFactor`
- [ ] Drawdown check on 60s cadence
- [ ] Rank update on 5-minute cadence; rebalance per user's `rebalanceCadenceSec`
- [ ] Fee crystallization on NAV > HWM × (1 + FEE_THRESHOLD)
- [ ] REST endpoints: `POST /v1/users/{user}/meta-strategy`, `GET /v1/users/{user}/dashboard`, `GET /v1/strategies`, `WS /v1/users/{user}/events`
- [ ] Registered on `AllocatorRegistry` with `isReferenceBrand = true`, name `"Helios Sentinel"`

### SX — Reputation Engine (v1 placeholder)
- [ ] Consumes Goldsky events (polling every 60s)
- [ ] **Phase 1 simplification**: compute a basic score from realized P&L + proof validity only (the full §8.2 formula lands in Phase 2)
- [ ] Sign updates with `REPUTATION_SIGNER_PK`, post to `ReputationAnchor.postReputationUpdate`
- [ ] Emit WebSocket feed for dashboard

### SX — Oracle (Phase 1 minimum)
- [ ] Price oracle signs 1-minute snapshots for WKITE, USDC.e, WETH
- [ ] Poseidon-chain of last N snapshots exposed via HTTP
- [ ] Root committed on-chain (simple signed anchor, full circuit-committed root acceptable in Phase 2)

### SX — Subgraph
- [ ] `subgraph.yaml` indexes Kite testnet contracts deployed in Phase 1
- [ ] Entities: `Strategy`, `Allocator`, `User`, `Allocation`, `Trade`, `NAVSnapshot`, `ReputationSnapshot`, `DefundEvent`
- [ ] Mappings for: `StrategyRegistered`, `AllocationCreated`, `TradeAttested`, `NAVReported`, `ReputationUpdated`, `StrategyDefunded`, `AllocatorRegistered`
- [ ] Deployed to Goldsky; read endpoint wired to services + frontend

### SX — Scenario mode
- [ ] `services/oracle` supports `SCENARIO_MODE=1` env that replays a deterministic price series from `scenarios/phase1-drawdown.json`
- [ ] Scenario: momentum strategy allocated → price drops to trigger 15%+ drawdown → auto-defund fires → replacement strategy takes the capital
- [ ] `scripts/e2e-scenario.sh` runs the full stack in scenario mode and asserts the expected end state
- [ ] Runs in CI as the end-to-end integration test

### FE — Frontend minimum
- [ ] `/onboard` — template picker (Conservative/Balanced/Aggressive), customization panel (asset universe, max per-strategy, drawdown threshold, max fee rate, rebalance cadence), plainspoken commitment summary, sign via Passport
- [ ] `/dashboard` — top strip (total NAV, today's P&L, all-time P&L, fees-to-date), current allocator card, active allocations table, live activity rail (WebSocket), withdraw control always visible
- [ ] `/strategies` — public directory table, sortable by every column, filter by class/chain/reputation
- [ ] Activity rail renders `StrategyAllocated`, `TradeAttested` (with shield), `StrategyDefunded`, `RebalanceComplete` events with mechanical (not smooth) appearance
- [ ] Row for a defunded strategy gets red left-border per `DESIGN.md §10.2` motion spec
- [ ] No sunburst yet (Phase 4)

### Acceptance for Phase 1
- [ ] Signature-to-first-trade in <60s in scenario mode
- [ ] Auto-defund scenario runs end-to-end with no manual intervention: Passport signature → UserVault deploy → Sentinel allocation → momentum strategy executes `executeWithProof` with real Groth16 proof → `TradeAttested` emitted → Reputation Engine posts update → scenario drives drawdown → `defundStrategy` fires (permissionless path tested) → replacement allocation lands → dashboard reflects every step
- [ ] `forge coverage` ≥ 85% on Phase 1 contracts
- [ ] A fresh clone + `pnpm dev` + scenario run succeeds on a clean laptop within 10 minutes

---

## Phase 2 — Widen strategy classes + full reputation math

**Goal.** Three classes with real proofs. Reputation is the full §8.2 formula.

### CX — Mean reversion circuit
- [ ] `circuits/mean_reversion_v1.circom` — N-sigma deviation signal, structurally similar to momentum with inverted direction logic; ≤ 20k constraints
- [ ] Unit tests: valid short on N-sigma up, valid long on N-sigma down, exit on mean re-cross, boundary cases
- [ ] Verifier deployed + registered

### CX — Yield rotation circuit
- [ ] `circuits/yield_rotation_v1.circom` — proves rate differential between `M_from` and `M_to` exceeds threshold against committed yield-oracle root; both markets in allowlisted universe; ≤ 15k constraints
- [ ] Unit tests: valid rotation, rejected rotation when APY differential below threshold, rejected market not in universe
- [ ] Verifier deployed + registered

### SX — Reference strategies for the new classes
- [ ] `reference-strategies/mean_reversion_v1/` — Python impl on SDK, deployed to VPS
- [ ] `reference-strategies/yield_rotation_v1/` — scans allowlisted lending markets (Phase 5 adds cross-chain; Phase 2 uses Kite-local markets only)
- [ ] Both registered on `StrategyRegistry` with real stake

### SX — Full reputation formula
- [ ] `PerformanceScore` — 0.5×7d + 0.3×30d + 0.2×90d normalized Sharpe; cohort-relative (median/IQR per class)
- [ ] `RiskScore` — `1 - clip(MaxDD90d / 5000, 0, 1)`
- [ ] `ProofScore` — `ValidProofs / TotalProofAttempts`
- [ ] `StakeScore` — `log(1 + stake/1000) / log(1 + max_stake_in_class/1000)`
- [ ] `AgeScore` — `clip(sqrt(trades_attested / 1000), 0, 1)`
- [ ] Weights w_perf=0.40, w_risk=0.25, w_proof=0.15, w_stake=0.10, w_age=0.10
- [ ] Unit tests validate each component against `Helios.md §8.2` worked examples
- [ ] `/audit` page exposes the inputs for every strategy's current score

### SX — Oracle hardening
- [ ] Yield oracle signs APY snapshots per lending market (Aave, Compound stubs for now — real integrations in Phase 5)
- [ ] Price oracle Poseidon-root anchored on-chain via a periodic commit
- [ ] Scenario mode supports scripted yield differentials for yield-rotation demos

### SX — Strategy SDK v0.1
- [ ] `pip install helios-strategy-sdk` works from a test-PyPI mirror
- [ ] `StrategyAgent` base class with `declared_class`, `asset_universe`, `max_position_size_usd`, `fee_rate_bps`, `on_bar`, `size_trade`, `should_exit`
- [ ] Backtest harness: `helios backtest --strategy ./my.py --period 90d --capital 10000` runs against historical replay and outputs a P&L/Sharpe/max-DD report
- [ ] Local simulator: `helios simulate` runs against mocked market, usable in CI
- [ ] Deploy helper: `helios deploy --strategy ./my.py --vps user@server` packages Docker image and bootstraps the agent
- [ ] Stake management: `helios stake top-up --amount N`
- [ ] Proof testing: `helios test-proof --trade <spec>` runs a full proof cycle locally
- [ ] Docs: `docs/operator-guide.md`

### Acceptance for Phase 2
- [ ] Multiple strategies of each class registered with non-zero capital
- [ ] Reputation scores visibly diverge based on realized performance + drawdown
- [ ] Backtest reports for each reference strategy committed under `docs/backtests/<class>_90d.md`
- [ ] External contributor could, in principle, publish a new momentum strategy using only the SDK + public docs

---

## Phase 3 — AllocatorSDK + Helix

**Goal.** Marketplace mechanism is real. Two allocators on-chain, users can pick.

### SX — Allocator SDK
- [ ] `packages/allocator-sdk` with `BaseAllocator`, `rank_strategies`, `allocate` abstract methods
- [ ] Helpers: `default_top_k_allocation`, `score_weighted_allocation`, `pairwise_correlation_from_goldsky`, `btc_realized_vol_30d`, `detect_regime`
- [ ] SDK handles: onboarding, drawdown monitoring at 60s, fee crystallization, defund/rebalance tx submission via Passport sessions, Goldsky integration, ReputationAnchor integration for allocator reputation, WS event emission, stake management, Docker packaging, local backtest
- [ ] CLI: `helios-allocator init | backtest | simulate | stake | deploy | logs`

### SX — Helix (second reference allocator)
- [ ] `services/helix/` built **entirely on top of allocator-sdk** — treated as an external consumer for validation purposes
- [ ] `helix_fee_factor` — regime-adaptive per `Helios.md §11.4.1(a)`
- [ ] `detect_regime` from BTC realized-vol percentiles
- [ ] `helix_greedy_pick` — correlation-aware greedy selection with `max_pairwise_correlation = 0.7`
- [ ] Registered on `AllocatorRegistry` with `isReferenceBrand = true`, name `"Helios Helix"`, fee rate 600 bps
- [ ] Runs alongside Sentinel on the VPS

### SX — Allocator reputation
- [ ] Reputation Engine computes allocator scores from aggregate user net P&L above HWM, drawdown discipline (did they actually fire bad strategies on time?), user retention, stake
- [ ] `postReputationUpdate` with `actor_type = ALLOCATOR`
- [ ] Allocator leaderboards queryable via subgraph

### FE — Allocator surface
- [ ] `/allocators` directory: Sentinel first with "Official Reference" badge, Helix second (same badge), space for third parties below
- [ ] Each card: name, fee rate, supported classes, ranking function one-sentence + "view code" link, current users, total capital managed, reputation, stake
- [ ] Side-by-side comparison mode (select 2+)
- [ ] `/onboard` adds an allocator-picker step
- [ ] `/allocators/[name]` detail page

### Acceptance for Phase 3
- [ ] A user picks Sentinel at onboarding → flow works. Same user re-onboards picking Helix → flow works with different allocation decisions visible.
- [ ] `helios-allocator init --name "TestThirdParty"` scaffolds a working allocator that can be registered on Kite testnet without any modifications to Helios code.
- [ ] Allocator leaderboard on dashboard shows both Sentinel and Helix with diverging reputation as their decisions play out differently across users.

---

## Phase 4 — Frontend completion + sunburst + Telegram

**Goal.** Every DESIGN.md surface implemented. Signature moments land.

### FE — Remaining pages
- [ ] `/` landing — confident headline, live stats band from subgraph (total capital managed, active strategies, attested trades, active allocators), two primary CTAs, secondary links. No feature sections, no testimonials, no FAQ.
- [ ] `/strategies/[id]` — manifest header, reputation breakdown panel (perf/risk/proof/stake/age), P&L curve with drawdown envelope, recent trades table with shield icons, current allocators, NAV timeline
- [ ] `/audit/[strategy]` — every trade paginated, proof hash + verification result, "verify this proof yourself" modal, reputation-calculation inputs exposed, JSON dump link. Celebrated ZK treatment per `DESIGN.md §12`.
- [ ] `/judge` — video link, "Try the demo scenario" button, contract addresses with explorer links, GitHub links, `verify-trade.js` command block, 5-step eval checklist, live transaction counts
- [ ] `/docs` — embedded operator + allocator guides

### FE — Sunburst viz
- [ ] Bespoke d3 implementation (not Recharts/Nivo primitive)
- [ ] Concentric rings: user → allocator → strategies → positions
- [ ] Segments sized by capital weight, colored by chain
- [ ] Amber selected state
- [ ] Hover reveals strategy name + allocated + NAV + P&L
- [ ] Click navigates to strategy detail
- [ ] Mechanical step animation on update (~300ms of ticked motion, not smooth)
- [ ] Mini-sunburst variant for allocator cards

### FE — Signature interactions
- [ ] Cascade — staggered 80–120ms stages across sunburst + table + activity rail
- [ ] Auto-defund — row red-border, NAV ticks to zero over 2s, sunburst rebalances, replacement row appears, activity rail prints both events. Total ~5–6s. Thermostat-kicking-on feel.
- [ ] Cross-chain rep update — chain badge pulse, in-flight indicator, resolve on arrival (don't hide LayerZero latency)

### FE — System polish
- [ ] Keyboard navigation per `DESIGN.md §5.5`: `J/K`, `/`, `Esc`, `G D`, `G S`, `G A`, `?` shortcut menu
- [ ] Reduced-motion media query reduces every signature interaction to instant
- [ ] Focus rings visible and amber-toned
- [ ] WCAG AA contrast audit passes across all pages
- [ ] Projector legibility check (low-contrast crush test on 1080p)

### FE — Telegram bot
- [ ] `@helios_market_bot` deployed, token in `TELEGRAM_BOT_TOKEN`
- [ ] Event subscriptions consume the allocator WS stream
- [ ] Message templates per `DESIGN.md §15`:
  - [ ] `StrategyAllocated`, `StrategyDefunded`, `RebalanceComplete`, `FeeAccrued`, `WithdrawalReady`
  - [ ] Each ≤ 200 chars, one event per message, restrained emoji (⚡/⚠️/✓ only), links to OKLink
- [ ] User opt-in flow from `/dashboard`

### Acceptance for Phase 4
- [ ] All surfaces from `DESIGN.md §9` live
- [ ] Scenario mode from Phase 1 replays at full visual fidelity — cascade animates staggered, auto-defund lands as thermostat moment, Telegram pings in sync
- [ ] An external designer reviewing the live app says "Bloomberg meets Vercel v0," not "DeFi app"

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
- [ ] Slither / Mythril / Echidna **clean** on every Phase 1 contract before any mainnet tx
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
- [ ] Echidna property tests for: vault solvency, no allocation exceeds meta-strategy bounds, only drawdown-breached strategies can be permissionlessly defunded, reputation never overflows
- [ ] Circuit unit tests for every class cover: zero inputs, max inputs, boundary conditions, every invariant branch
- [ ] Internal threat model walkthrough against `Helios.md §15.2` — every row has a test or a documented mitigation

### OP — Deploy hardening
- [ ] PM2 ecosystem file for all services with auto-restart, log rotation
- [ ] Nginx reverse proxy with rate limiting on public endpoints
- [ ] Health-check endpoints monitored; alerting to a Telegram admin channel
- [ ] Postgres backups + restore runbook
- [ ] Secrets in VPS env only, never committed

### Docs
- [ ] `docs/operator-guide.md` — how to ship a strategy
- [ ] `docs/allocator-guide.md` — how to ship a competing allocator
- [ ] `docs/reputation-math.md` — the §8 formula, annotated + worked examples
- [ ] `docs/circuit-specs.md` — Circom circuit invariants per class
- [ ] `docs/threat-model.md` — §15 rendered as a standalone doc
- [ ] `docs/audit-checklist.md` — for external auditors
- [ ] Backtest reports at `docs/backtests/` for every reference strategy
- [ ] `README.md` — judge-friendly entry, links to demo video, live URL, /judge page, repo map

### Demo
- [ ] 3-minute live demo script rehearsed end-to-end
- [ ] 90-second backup video recorded and hosted
- [ ] Demo setup runbook: which services to start, which scenario to load, which browser window to open first
- [ ] Cold-start verification: fresh VPS + git clone + `docker-compose up` + env file → Phase 1 scenario passes within 10 minutes

### Acceptance for Phase 6
- [ ] A cold judge following `/judge`'s 5-step checklist completes evaluation in under 5 minutes
- [ ] Judge can verify a ZK proof independently against an on-chain tx and confirm it matches
- [ ] Slither/Mythril/Echidna all pass (or every finding documented + justified)
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
