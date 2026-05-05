# CLAUDE.md

Operational guide for Claude Code sessions working in this repo. Read this first, then refer to `Helios.md` (spec) and `DESIGN.md` (design brief) for depth.

---

## What Helios is

A programmatic capital market for AI trading agents on the Kite chain. Users sign one meta-strategy; an **Allocator Agent** autonomously routes their capital across competing **Strategy Agents**; every trade carries a Groth16 ZK proof binding it to the strategy's declared class; reputation accrues from realized, attested performance and flows across chains via LayerZero.

- **Product spec** → `Helios.md` (source of truth for behavior, contract interfaces, reputation math, ZK circuits, economics)
- **Design brief** → `DESIGN.md` (source of truth for aesthetic, density, motion, signature interactions)
- **Current phase status** → `TODO.md`
- **Build plan** → `/home/emark/.claude/plans/i-want-to-start-jiggly-hare.md`

When these documents conflict with something in the code, the documents win unless there's a deliberate, reasoned deviation logged in the relevant phase in `TODO.md`.

---

## Repo map

Intended layout (being scaffolded in Phase 0; current state may be partial — check `TODO.md`):

| Path | Purpose |
|---|---|
| `contracts/` | Foundry project. All Solidity, tests, per-chain deploy scripts, deployed addresses in `deployments/`. |
| `circuits/` | Circom circuits (`momentum_v1`, `mean_reversion_v1`, `yield_rotation_v1`), PTAU artifacts, snarkjs build output. |
| `packages/strategy-sdk/` | Public `helios-strategy-sdk` Python package. Implement `StrategyAgent`, ship a strategy. |
| `packages/allocator-sdk/` | Public `helios-allocator-sdk` Python package. Implement `BaseAllocator`, ship a competing allocator. |
| `packages/helios-cli/` | Python CLI wrapping both SDKs (`helios backtest`, `helios deploy`, `helios-allocator init`, ...). |
| `packages/contracts-abi/` | **ABI freeze module.** Shared TypeScript/Python bindings generated from Foundry artifacts. Services, subgraph, and frontend all import from here — never duplicate ABI fragments elsewhere. |
| `services/sentinel/` | Reference allocator (FastAPI). The simple baseline allocator in the marketplace. |
| `services/helix/` | Second reference allocator, built on `allocator-sdk`. Correlation-aware, regime-adaptive. |
| `services/reputation/` | Reputation engine. Reads Goldsky → computes scores → signs → posts to `ReputationAnchor`. |
| `services/prover/` | Node.js HTTP wrapper around snarkjs. Generates Groth16 proofs from trade specs. |
| `services/oracle/` | Helios-operated price + yield oracle (signs 1-minute snapshots, Poseidon-committed chain). |
| `services/bot/` | `@helios_market_bot` Telegram bot — text-forward event pings. |
| `frontend/` | Next.js 14 App Router, TypeScript, Tailwind with CSS-variable design tokens, wagmi v2 + viem. |
| `reference-strategies/` | The three reference strategy implementations built on `strategy-sdk`. |
| `subgraph/` | Goldsky subgraph (`subgraph.yaml`, `schema.graphql`, mappings in `src/`). |
| `deploy/` | VPS deployment scripts — PM2, Nginx, Dockerfiles per service. |
| `docs/` | Long-form: operator-guide, allocator-guide, reputation-math, circuit-specs, threat-model, audit-checklist. |
| `docker-compose.yml` | Single-command full-stack local boot. |

---

## Running the stack

Prerequisites: Node 20+, pnpm 9+, Python 3.11+, `uv`, Foundry (`curl -L https://foundry.paradigm.xyz | bash`), Circom 2.1.9+, Docker.

```bash
# First-time setup
pnpm install                           # installs JS/TS workspaces
uv sync                                # installs Python workspaces
forge install                          # installs Solidity deps in contracts/

# Full-stack local boot (Phase 0+)
pnpm dev                               # docker-compose up + all services + frontend

# Per-surface dev loops
forge test -vv                         # contracts (from contracts/)
forge coverage                         # coverage report
pnpm --filter frontend dev             # frontend hot-reload at :3000
python -m services.sentinel            # allocator service (respects SENTINEL_* env vars)
python -m services.reputation          # reputation engine
npm --prefix services/prover run dev   # prover service
pnpm --filter subgraph codegen         # regenerate subgraph types after schema change
pnpm --filter subgraph deploy          # deploy to Goldsky (requires GOLDSKY_API_KEY)

# Circuits
cd circuits && make momentum_v1        # compile + witness gen + zkey + Verifier.sol
make test                              # circuit unit tests (zero/max/boundary)
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in. Required for running the full stack:

| Variable | Used by | Notes |
|---|---|---|
| `KITE_RPC_URL` | contracts, services, subgraph | Kite testnet RPC (chain id 2368) |
| `BASE_SEPOLIA_RPC_URL` | contracts, services | Phase 5+ |
| `ARBITRUM_SEPOLIA_RPC_URL` | contracts, services | Phase 5+ |
| `KITE_PASSPORT_SIGNER_PK` | services | Passport root key for the demo user (never commit) |
| `REPUTATION_SIGNER_PK` | services/reputation | Registered signer posting to `ReputationAnchor` |
| `ORACLE_SIGNER_PK` | services/oracle | Price/yield oracle signing key |
| `DATABASE_URL` | services | Postgres connection string |
| `GOLDSKY_API_KEY` | subgraph | Required to deploy the subgraph |
| `GOLDSKY_ENDPOINT` | services, frontend | Read endpoint for the subgraph |
| `TELEGRAM_BOT_TOKEN` | services/bot | `@helios_market_bot` token |
| `VERCEL_TOKEN` | deploy scripts | Frontend deploy |
| `VPS_SSH` | deploy/ | e.g. `user@vps-host` |

Secrets never go in the repo. Use `.env` for local, Vercel/VPS env for prod.

---

## Conventions

### Solidity (contracts/)

- Foundry, `forge fmt` on every save. CI fails on unformatted code.
- Named imports only (`import {Foo} from "./Foo.sol"`) — no unnamed imports.
- UUPS upgradeable pattern **only** for vaults (`UserVault`, `AllocatorVault`, `StrategyVault`). Registries and anchors are immutable.
- All cross-contract calls gated by the tightest possible modifier (`onlyOwner`, `onlyAllocator`, `onlyReputationAnchor`, `onlyOApp`).
- Every external-facing function emits an event. Subgraph depends on this.
- Target ≥ 85% branch coverage before Phase 5 starts; 90% before submission.

### Python (services/, packages/)

- `uv` for dependency management, `ruff` for lint+format, `pyright` for typechecking. All three run in CI.
- Async-first — every service is FastAPI + asyncio. No sync I/O in hot paths.
- Public SDK APIs use `pydantic` v2 models; internal services can use dataclasses.
- Module-level: never log secrets; use `structlog` with JSON output for production.

### TypeScript (frontend/, packages/contracts-abi/)

- `strict: true`, no `any`, no `@ts-expect-error` without a comment explaining why.
- Tailwind tokens live in `frontend/src/styles/tokens.css` as CSS variables; `tailwind.config.ts` mirrors them. **Never hardcode colors in JSX** — if a token is missing, add it to both files.
- No stock icon libraries used as-is. Lucide icons are restyled via `frontend/src/components/icon/` wrappers to match system stroke weights.

### Commits & branches

- Conventional commits (`feat:`, `fix:`, `chore:`, `test:`, `docs:`, `refactor:`).
- Branch per phase: `phase-0-bootstrap`, `phase-1-vertical-slice`, etc. Sub-branches for tracks (`phase-1-contracts`, `phase-1-circuits`).
- PR titles: `[Phase N][track] Short imperative summary`.

---

## Key addresses

Deployed contract addresses per chain live in `contracts/deployments/*.json`, auto-written by deploy scripts. Frontend and services read from these files — no hardcoded addresses elsewhere. Current snapshot:

- **Kite testnet (2368)** — Phase 2 deployed; full set in `contracts/deployments/kite-testnet.json`. Pinned references:
  - `userVault` `0x78b3515f4e9186d9870dcef02da58e4c8c5c6e8f`
  - `allocatorVault` `0xf3e4452fe17edbfa6833022b9c186aa14b98955d`
  - `strategyRegistry` `0x3a0f5b9436eca0c8c0eced659dcc41e86e65e33d`
  - `allocatorRegistry` `0xbfeba025ca32324a87c620a5c7c110c7666f417c`
  - `tradeAttestationVerifier` `0x743e1bd7e9795e78b10965eaeaa93bf215476c96` (TAV; class map rotated 2026-05-05 to the priority-2 verifier adapters below)
  - Verifier adapters (current, post-priority-2 redeploy):
    - momentum_v1 → `0xfd03cc2cfcb688d7f92b5c4d61ca83d7a400c805` (raw `0x243f148043067aa405def7420351a50ec15b7551`)
    - mean_reversion_v1 → `0x9ea786e6dc8afeb016d0b8a1c5f6f5512808a171` (raw `0x37b8fb60e2333834d604d1f5cec965094c025529`)
    - yield_rotation_v1 → `0xbd300b35f824ec2586b36113025d511ed07434d7` (raw `0xf42daa10f5105ae6dd8b138ff655d8c09c8574b1`)
  - `reputationAnchor` (V1, registry-bound) `0x51c07adf596b1e72697a9b8232d061ed006943dc`
  - `reputationAnchorV2` (sidecar; not registry-bound until Phase-5 cutover — see `docs/reputation-v1-v2-cutover.md`) `0x735680a32a0e5d9d23d7e8e8302f434e7f30428e`
  - `oraclePriceAnchor` `0x90e7a456404e73466e71a190dbb5a5a3490776a8`
  - `oracleYieldAnchor` `0x1e458d57f9fe0cf50f82366c258b05a254d8fa6f`
  - Three deployed strategy vaults per class (base + Variant2 + Variant3); see JSON for the full nine.
- **Kite mainnet**: *(Phase 6 — judge demo deployment per hybrid strategy in `docs/deployment-strategy.md`)*
- **Base Sepolia (84532)**: *(Phase 5)*
- **Arbitrum Sepolia (421614)**: *(Phase 5)*

---

## Before you touch X

**Before modifying a contract:**
1. Read the spec section for that contract (`Helios.md §6.*`).
2. Run `forge test -vv` to establish baseline.
3. If the ABI changes, regenerate `packages/contracts-abi/` (`pnpm --filter contracts-abi build`) and update every downstream consumer.

**Before modifying a circuit:**
1. Read `Helios.md §9` for the class's invariants.
2. Run circuit tests (`cd circuits && make test`).
3. If constraints shift materially, re-check PTAU headroom (PTAU 16 = ≤65k constraints).
4. Regenerate the Solidity verifier and redeploy through the deploy script.

**Before adding a new strategy class:**
Full checklist — all must happen or the class is incomplete:
1. Circom circuit in `circuits/<class>.circom` + unit tests
2. Generated `<Class>Verifier.sol` deployed via `contracts/script/DeployVerifier.s.sol`
3. Registered in `TradeAttestationVerifier.verifiersByClass`
4. `StrategyAgent` subclass in `packages/strategy-sdk/helios/classes/<class>.py`
5. Reference implementation in `reference-strategies/<class>/`
6. Subgraph entity + mapping for class-specific fields
7. Frontend filter option on `/strategies`
8. Backtest report in `docs/backtests/<class>_90d.md`

**Before changing the reputation formula:**
It's spec'd in `Helios.md §8.2` with specific weights. Changes require updating: the engine (`services/reputation/`), the docs (`docs/reputation-math.md`), and the `/audit` page explainer. Any weight change is a v2 decision, not a drop-in edit.

**Before changing motion or color:**
Check `DESIGN.md §13` (motion) and `§4.3` (color). Amber is ~2–5% of pixels total; green/red are data-signal only; no smooth easings on anything that maps to a discrete on-chain event.

---

## Testing discipline

- **Contracts**: Foundry unit tests per contract + invariant tests for state-changing flows. Slither + Mythril run in CI from Phase 6.
- **Circuits**: input unit tests covering zero, max, and boundary cases; proof generation tested end-to-end against the deployed verifier.
- **Services**: pytest + httpx against a docker-compose stack; scenario-mode replay runs as an integration test.
- **Frontend**: Playwright for the three signature interactions (cascade, auto-defund, cross-chain rep update). Component snapshots via Storybook from Phase 4.
- **End-to-end**: `scripts/e2e-scenario.sh` runs the Phase 1 vertical-slice scenario against a fresh stack. Required to pass before any release tag.

---

## Current phase

Phase 0 — Bootstrap & ground truth. See `TODO.md` for the live checklist.
