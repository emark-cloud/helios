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
| `KITE_RPC_URL` | contracts, services, subgraph | Kite testnet RPC, e.g. `https://rpc-testnet.gokite.ai/` (chain id 2368). Mainnet RPC is `https://rpc.gokite.ai/` (chain id 2366) if we elect the mainnet stretch. |
| `BASE_SEPOLIA_RPC_URL` | contracts, services | Phase 5+ |
| `ARBITRUM_SEPOLIA_RPC_URL` | contracts, services | Phase 5+ |
| `KITE_PASSPORT_SESSION_ID` | services, frontend | Passport session token issued by the `kpass` CLI for the demo user. Passport wallets are MPC-backed — they do NOT expose raw private keys, so do not use a `*_SIGNER_PK` variable here. Same variable on testnet and mainnet; the chain target is set by `KITE_PASSPORT_NETWORK` (`kite-testnet` for v1; `kite-mainnet` only if we exercise the mainnet stretch). |
| `REPUTATION_SIGNER_PK` | services/reputation | Registered signer posting to `ReputationAnchor` |
| `ORACLE_SIGNER_PK` | services/oracle | Price/yield oracle signing key |
| `DATABASE_URL` | services | Postgres connection string |
| `GOLDSKY_API_KEY` | subgraph | Required to deploy the subgraph |
| `GOLDSKY_ENDPOINT` | services, frontend | Read endpoint for the subgraph |
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

- **Kite testnet (2368)** — Phase-6 real-price cutover live (broadcast 2026-05-09, `docs/phase6-realprice-plan.md`); full set in `contracts/deployments/kite-testnet.json`. **WS11 V1→V2 cutover live 2026-05-11** (`docs/phase5-xchain-verification.md` §WS11): fresh `reputationAnchorV2Bis` `0x2b6c5f3648Ae2aA27c80CB871590D1Ef1346938D` + `strategyRegistryV3` `0xe6c2cfCa8fd59f4b6fCF0b5F83A515aBB7498D35` + `allocatorRegistryV2` `0xb673e6F8f11fb416B47f5d9C0a36400bF9485A06` (registries immutably bound to v2-bis at construction); AllocatorVault + 9 Phase-6 vaults rebound to SR-v3 via `setRegistry`/`setStrategyRegistry` setters added in `allocatorVaultImplWS11` / `strategyVaultImplWS11`; new `heliosOApp` `0x9845c0C697964464dCAF2602b4e516CaEA98E51E` (v2-bis-bound, peers re-wired Base + Arb); subgraph `helios/v0.8.0` (CXR-4 cutover 2026-05-13; v0.7.2 deleted from Goldsky after being superseded so the new `helios-base/v0.8.0` + `helios-arbitrum/v0.8.0` venue subgraphs fit alongside under the 3-subgraph free-tier limit. v0.8.0 carries the `getOrCreateStrategy` chainId-init change so Trade-bootstrapped strategies on Base/Arb surface their execution chain. Pre-CXR-4 history — v0.7.0 srcChainId crash → v0.7.1 fix in commit `0375944` → v0.7.2 `handleStrategySlashed` in commit `88fc1e5` against phantom EOAs surveyed in `project_phantom_strategy_cleanup` — retained in commit log only). The legacy `strategyRegistry` (V1), `strategyRegistryV2` (WS9), `reputationAnchor` (V1), and `heliosOApp` predecessor (`0x7Bad5250…` null-anchor) are parked but no longer authoritative — engine + frontend + VPS all point at the WS11 surface. Pinned references:
  - `userVault` `0x78b3515f4e9186d9870dcef02da58e4c8c5c6e8f` (impl `0x245a96310b228016d79f6b93d934eb26c1FcE209`, Phase-3 Unit-1 redeploy 2026-05-08 with Pausable + setMeta tightening guard from HIGH #5/#10)
  - `allocatorVault` `0xf3e4452fe17edbfa6833022b9c186aa14b98955d` (impl `0x770E3078a285651c11863Ec4D8Be87D0aDE29Cb7`, Phase-3 Unit-1 redeploy 2026-05-08 with Pausable + `userTotalDeployed` view + capped `_unwindAndCredit` from HIGH #5/#8/#10)
  - `strategyRegistry` `0x3a0f5b9436eca0c8c0eced659dcc41e86e65e33d` (V1, Phase-1 deploy; predates `paramsHashOf`/`commitInitialParamsHash` from PR #70 / commit `4674f61`. AllocatorVault references this registry as immutable, so it stays the active-flag source of truth)
  - `strategyRegistryV2` `0x7e707c8a2ce38dc43084a8205e18a6bfd731c5c2` (WS9 redeploy 2026-05-10; current source compile, has `paramsHashOf` + `commitInitialParamsHash`. Phase-6 vaults' init-time `registry` field points here so `_activeParamsHash` resolves; vaults are also dual-registered in V1 so the AllocatorVault check passes)
  - `allocatorRegistry` `0xbfeba025ca32324a87c620a5c7c110c7666f417c`
  - `tradeAttestationVerifier` `0xd54C6b8C0AD19F815996d45F7C0A2419CB159017` (TAV; **Phase-6 cross-decimal cutover 2026-05-12**, fresh deploy with `CHANGE_DELAY = 0` so the 16-PI verifier set could be registered first-time via `registerVerifier`. Supersedes Phase-6 #13 `0x3698F60a…` which had `CHANGE_DELAY = 2 days` baked in as a `constant` and no in-place rotation path for the cross-decimal Constraint-2 fix.)
  - Verifier adapters (current, post-cross-decimal cutover 2026-05-12 — 16 public inputs, price-aware Constraint 2, decimals honesty enforced by `StrategyVault._validateAndVerify` via `IERC20Metadata.decimals()`):
    - momentum_v1 → `0x13424B7e1B03E9C820872dC76904bFb63758DBbe` (raw `0xb2cB0F96bB3e0056166688801E4a38e750D73737`; supersedes legacy `0x66d2eb52…` which was 14-PI same-unit slippage and rejected every cross-decimal swap with `TooLittleReceived`)
    - mean_reversion_v1 → `0x5967AFC6770dA8130eE7fF56a429916650FeE497` (raw `0xc7251d0ec250cD36E04db57a4eea7E6d34B1A723`; same shape change — supersedes legacy `0xd52F10D7…`)
    - yield_rotation_v1 → `0xB0FBa2997206429712873eC65486f3119982608E` (raw `0x159fA2006C3d37A599a7d47b34f6a7dB82E4c109`; YR re-deployed only to register against the new TAV — its constraint set is unchanged from the prior `0xda1572e9…`)
  - Strategy vault impl (UUPS) `0xb73994FE82D253d4d2eFaAB9Cd220565b4de4104` (2026-05-12 cross-decimal cutover; 16-PI directional path, decimals-honesty validation; `migrateVerifier(address)` re-pointed all 9 Phase-6 proxies at the new TAV in a single `upgradeToAndCall` per proxy.)
  - `reputationAnchor` (V1, registry-bound) `0x51c07adf596b1e72697a9b8232d061ed006943dc`
  - `reputationAnchorV2` (sidecar; not registry-bound until Phase-5 cutover — see `docs/reputation-v1-v2-cutover.md`) `0x735680a32a0e5d9d23d7e8e8302f434e7f30428e`
  - `oraclePriceAnchor` `0x566e1f1b5bd7109f2c86805e2c092502d1b2f9f4` (Phase-3 redeploy 2026-05-07; supersedes `0x90e7a456…` which lacked `freshness()` / `unrevokeRoot()` from HIGH #6/#9)
  - `oracleYieldAnchor` `0x345cd375ec42476eb95c5903fb3abb27f9400f9d` (Phase-3 redeploy 2026-05-07; supersedes `0x1e458d57…`)
  - Test universe (Phase-6 broadcast 2026-05-09 via `DeployTestUniverse.s.sol`):
    - `usdc` (mUSDC, 18 dec, existing) `0xe8cf8a5711f08d5211d46a2835ecc9c9af1b91cd`
    - `mWbtc` `0x3f81a60c5d5c6bfcb415080b846da22903ff37a0` (8 dec; 1k seeded into MockSwapRouter)
    - `mWeth` `0x789ff10eb109626b01816161be72c9df32be4a00` (18 dec; 50k seeded)
    - `mSol` `0xcf1276516a625723e40ae13d598de837079ad532` (9 dec; 1M seeded)
    - `swapRouter` (MockSwapRouter, owner = deployer) `0x55782e7019f4619a06a25bf66d2998c8fe2cc436` — fed by VPS `RouterPriceMirror` keeper (`oracle.router_mirror.posted` log) every bar with 5 bps spread per leg.
  - Strategy vaults — **Phase-6 capacity-fix redeploy 2026-05-10** (`DeployPhase6MultiAssetVaults.s.sol`); nine new ERC1967 proxies on impl `0x934f7639e5Cb320e4394736f5663b53E9C6b5c7b`. Universe per class: mom/mr `[mUSDC, mWBTC, mWETH, mSOL]`; yr `[mUSDC]` (Helios.md §12.1 carve-out — yield venues live on Arbitrum). Distinct paramsHash per (class, variant) seeded as `keccak256("helios.<class>.phase6.multiasset.<variant>")`. All active in StrategyRegistry; the prior phase-6 nine are flipped `active=false` (`DeactivateLegacyVaults.s.sol`) — supersedes the 2026-05-09 cohort which used 6-dec `MAX_CAPACITY = 1_000_000e6` against an 18-dec mUSDC, capping each vault at ~1e-6 mUSDC and reverting every Sentinel `allocateToStrategy` with `CapacityExceeded()` (`0x9ff41fe0`). The 2026-05-10 cohort uses `MAX_CAPACITY = 1_000_000e18` and stake `5_000e18`.
    - **WS9 dual-registry redeploy 2026-05-10 (afternoon)**: morning's capacity-fix vaults could never satisfy `_activeParamsHash` because V1 registry predates `paramsHashOf`. Afternoon redeploy points each vault's init-time `registry` at V2 (`0x7e707c8a…`) and dual-registers in BOTH V1 (so AllocatorVault's active-check passes) and V2 (so executeWithProof's paramsHashOf resolves). Stake doubled: 90,000e18 mUSDC total. Deployer minted 100k extra mUSDC pre-broadcast.
    - `phase6VaultMomentum` `0xa44ef042840c8c4f1a174daf66389efeb8375a5a` (current; supersedes the WS9-afternoon dual-registry vault `0x35c07f855d10da4b09e5d6322a2155f0396e4311`, parked under `phase6VaultMomentumLegacy_dedicated_op_predecessor`, which itself superseded the morning capacity-fix vault `0xdadeac5d…`. The 2026-05-10 evening redeploy added the per-class dedicated operator/navOracle EOA to break shared-deployer nonce contention — memory `project_phase6_ws9_dedicated_keys.md`. Authoritative source: `contracts/deployments/kite-testnet.json → addresses.phase6VaultMomentum`)
    - `phase6VaultMomentumVariant2` `0x7a18727375065b29526d816b713fad99cd247006` (supersedes morning `0x96ea2d19…`)
    - `phase6VaultMomentumVariant3` `0xecfeb975789cf058865830f985ba18299d8e1dca` (supersedes morning `0xc05862ef…`)
    - `phase6VaultMeanReversion` `0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a` (current; supersedes the WS9-afternoon dual-registry vault `0xe09ed1ecb4bd9e6d64f9fd0270c95e4f17d98015`, parked under `phase6VaultMeanReversionLegacy_dedicated_op_predecessor`, which itself superseded the morning capacity-fix vault `0xf6d714e8…`. Same dedicated-keys lineage as `phase6VaultMomentum` above. **This is the vault that fired the first eight autonomous `TradeAttested` events on 2026-05-12** — see `docs/phase6-acceptance.md`. Authoritative source: `contracts/deployments/kite-testnet.json → addresses.phase6VaultMeanReversion`)
    - `phase6VaultMeanReversionVariant2` `0x4509c3e7b5e418c0701cf4d0145c570bac2f8fca` (supersedes morning `0xb95c141f…`)
    - `phase6VaultMeanReversionVariant3` `0x125b10809e3c6d70c51bf6385ed3cfb1c771d0f5` (supersedes morning `0x3d246570…`)
    - `phase6VaultYieldRotation` `0x2aff8735ed89451d359205dc6a80ae625e6f6e47` (morning `0x1caba93f…` retained `active=true` because it holds 55 mUSDC user NAV; deactivation deferred until defunded)
    - `phase6VaultYieldRotationVariant2` `0x7ed482adcc6951bc2058dd45cc26d15b3d585deb` (supersedes morning `0x660d8826…`)
    - `phase6VaultYieldRotationVariant3` `0x76a50fe4c5585a13be311eca135d0ab8f39b434d` (supersedes morning `0x42248ab4…`)
    Allocators auto-resolve through Goldsky's `where: { active: true }` filter (`AllocatorGoldsky.fetch_directory`) — no env-var change to switch the strategy set, the registry is canonical. Subgraph deployed at `helios/v0.8.0` (`https://api.goldsky.com/api/public/project_cmodpmbv1pkd70127d9g741ek/subgraphs/helios/v0.8.0/gn`); Base + Arb venue subgraphs at `helios-base/v0.8.0` + `helios-arbitrum/v0.8.0` under the same project. The mainnet stretch (if exercised) does a fresh deploy from a clean slate.
- **Kite mainnet**: *(Stretch — only if time permits; playbook in `docs/deployment-strategy.md`. Not in v1 scope.)*
- **Base Sepolia (84532)** — Phase-5 WS10 live-network verification (broadcast 2026-05-11; full set in `contracts/deployments/base-sepolia.json`). Pinned references:
  - `heliosOApp` `0x55782e7019f4619A06A25bf66D2998C8Fe2CC436` (LZ V2 OApp, `kiteEid=40415`, `reputationAnchor=address(0)` — execution-chain shape)
  - LZ V2 endpoint `0x6EDCE65403992e310A62460808c4b910D972f10f` (LZ EID `40245`)
  - Peers set to Kite (`0x9d93f3f2…`) and Arb (`0x55782e70…`)
  - **CXR-1 (2026-05-13)** — `strategyRegistry` `0x2a94DE11521EAF190e451863bEfe0F178f04DF32` (SR-v3 bytecode; gates mom.base + mr.base vaults)
  - **CXR-3 (2026-05-13)** — Base spot vaults live for §12.1 deep-liquidity routing:
    - `strategyVaultImpl` `0x735680A32A0e5d9d23D7e8e8302F434e7F30428E` (CXR-aware impl with `bridgeReceiver`/`oftAdapter`/`totalCrossChainAllocated` slots — supersedes the Phase-5 `0x78b3515f…` pre-CXR impl)
    - `phase6VaultMomentumBase` `0x9e14299e6FAeE1C1F352E2F9197D8A080306FE8d` (current — dedicated-ops redeploy 2026-05-13; `manifest.operator = navOracle = 0xf95Ba60e81bf483cFdc95Cfe52CCf3029ef09e03`; class MOM; baseAsset = Base mUSDC `0xe8CF8A57…` 6-dec; `allowedRouter` = Uniswap V3 SwapRouter02 `0x94cc0aac…`; assetUniverse = [mUSDC, WETH9 OP-Stack predeploy `0x4200…0006`]; stake 5_000 mUSDC; paramsHash committed `0x1a6f4e55…` via deployer since SR entry `operator=deployer` (registerStrategy caller); supersedes morning shared-deployer `0x90e7A456…` deactivated under `phase6VaultMomentumBaseLegacy_morning_shared`).
    - `phase6VaultMeanReversionBase` `0x8b375617589DBC7A90049b0fE07f2Fb4D5A19F08` (current — dedicated-ops redeploy 2026-05-13; `manifest.operator = navOracle = 0xA21Aaf25544cD43505B6e11512E1268Dbd453476`; class MR; same wiring as mom.base; stake 5_000 mUSDC; paramsHash committed `0x2857123e…`; supersedes morning shared-deployer `0x1e458D57…` deactivated under `phase6VaultMeanReversionBaseLegacy_morning_shared`).
- **Arbitrum Sepolia (421614)** — Phase-5 WS10 live-network verification (broadcast 2026-05-11; full set in `contracts/deployments/arbitrum-sepolia.json`). Pinned references:
  - `heliosOApp` `0x55782e7019f4619A06A25bf66D2998C8Fe2CC436` (same address as Base — deployer EOA nonce sequence is identical on both freshly-used chains; LZ EID `40231`)
  - LZ V2 endpoint `0x6EDCE65403992e310A62460808c4b910D972f10f`
  - Peers set to Kite + Base
  - **CXR-1 + CXR-2 (2026-05-13)** — first remote execution surface for §12.1 venue routing:
    - `strategyRegistry` `0x21FBC51Ed4a063078b2a8B588508CeaAd7899ce2` (SR-v3 bytecode; `reputationAnchor_` placeholder = local HeliosOApp since reputation propagates Arb→Kite via the OApp pipe, never reverse; STAKE_COOLDOWN = 7 days; owner = deployer)
    - `phase6VaultYieldRotationArb` `0x516f23B9d2b6918D005d00Ccea3074cED1f8D005` (ERC1967 proxy; UUPS-upgraded 2026-05-13 to fresh CXR-aware impl `0x735680A32A0e5d9d23D7e8e8302F434e7F30428E` — supersedes the pre-CXR Phase-5 impl `0x78b3515f…` so the `bridgeReceiver` slot is now settable; state preserved); baseAsset = Arb-mUSDC `0xe8CF8A57…` 6-dec; `allowedRouter` = MockYieldVault `0xc065af9b…` Aave-V3-shaped lending venue; `allocatorVault` = deployer EOA placeholder for PI_ALLOCATOR binding until CXR-0b BridgeReceiver lands; stake 5_000 mUSDC, maxCapacity 1_000_000 mUSDC; paramsHash `keccak256("helios.yield_rot_v1.phase6.multiasset.arb")`; class YR; registered on Arb SR; `strategyCount = 1`. Real Aave V3 swap is a one-line `allowedRouter` flip once an Aave Arb-Sepolia faucet becomes accessible — admin-gated FiatToken USDC blocked v1 cutover.
    - `strategyVaultImplCXR` `0x735680A32A0e5d9d23D7e8e8302F434e7F30428E` (CXR-aware StrategyVault impl on Arb)
    - `mUsdc` (deployer mint authority retained, 6-dec on Arb vs 18-dec on Kite — different on-chain instances at the same address by nonce coincidence)
- **Kite testnet — Phase-5 cross-chain additions (2026-05-11)**:
  - `heliosOApp` `0x9D93F3f2254d7d6f6f4208938b7Ce7F9E33c43B3` (canonical-side OApp; wired to live V1 `reputationAnchor` `0x51c07adf…`. Constructor `kiteEid=40415`, `maxPendingPerStrategy=64`. Owner = deployer)
  - LZ V2 endpoint `0x3aCAAf60502791D199a5a5F0B173D78229eBFe32` (LZ EID `40415`)
  - V1 `ReputationAnchor.setOApp(heliosOApp)` landed in tx `0xabc5f4fb…` 2026-05-11 — pre-WS10 the field was `0x0`, so any inbound `postCrossChainUpdate(...)` reverted `NotOApp()`. Live-network verification in `docs/phase5-xchain-verification.md`.

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

**Before integrating Kite Passport:**
Passport supports Kite Testnet (chain 2368) and Kite Mainnet (chain 2366) with the **same** install / passkey / x402 flow — only the chain target differs. v1 runs real Passport against testnet through Phase 6; mainnet promotion is a stretch goal (flow is identical, only the chain target changes). There is no EIP-712 shim; the v0 spec's "user signs one meta-strategy" framing maps onto a Passport passkey-approved session, not a raw signing key. Reference: `Helios.md §12.1` (Passport on testnet subsection) and the testnet config table there.
- CLI install (same on both networks): `curl -fsSL https://agentpassport.ai/install.sh | bash`
- Testnet faucet: `https://faucet.gokite.ai`
- Testnet x402 facilitator: `0x12343e649e6b2b2b77649DFAb88f103c02F3C78b`
- Test payment token in Passport x402 examples: `0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63`
- Live x402 sample service: `https://x402.dev.gokite.ai/api/weather`

---

## Testing discipline

- **Contracts**: Foundry unit tests per contract + invariant tests for state-changing flows. Slither + Mythril run in CI from Phase 6 polish.
- **Circuits**: input unit tests covering zero, max, and boundary cases; proof generation tested end-to-end against the deployed verifier.
- **Services**: pytest + httpx against a docker-compose stack; scenario-mode replay runs as an integration test.
- **Frontend**: Playwright for the three signature interactions (cascade, auto-defund, cross-chain rep update). Component snapshots via Storybook from Phase 4.
- **End-to-end**: `scripts/e2e-scenario.sh` runs the Phase 1 vertical-slice scenario against a fresh stack. Required to pass before any release tag.

---

## Current phase

Phase 6 — Polish + submission. Phases 0–5 complete; `v0.5.0` tag
lands on `main` once the WS8 acceptance PR merges. WS1–WS7 already on
`main` via stacked PRs #82–#88; WS8 ships `scripts/preflight-phase5.sh`,
`scripts/measure_xchain_latency.py`,
`services/sentinel/tests/test_phase5_xchain.py`, and the
`scripts/e2e-scenario.sh phase5` mode. See `docs/phase5-acceptance.md`
for the WS8 evidence and `TODO.md` for the live Phase 6 checklist.

**WS9 — Autonomous attested trades** (active, gates WS5 + WS6). After
the Phase-6 capacity-fix redeploy + sentinel decimals/allocate fixes
landed 2026-05-10, the allocator chain works end-to-end (user →
allocator → 9 vaults holding capital), but no strategy has fired a
`TradeAttested` event yet because seven runtime misconfigs cascade.
See `docs/phase6-plan.md` §WS9 + the design doc at
`/home/emark/.claude/plans/dazzling-spinning-quokka.md`. Three layers:
oracle aliases + cadence (`services/oracle/src/oracle/service.py`),
strategy runtime wiring (`asset_universe_addresses`, `Web3BlockProvider`,
autonomous `commitInitialParamsHash` lifespan hook in each
`reference-strategies/*/service.py`), and VPS env updates (operator +
NAV PKs, anchor cadence, `*_ASSET_UNIVERSE_ADDRESSES_JSON`).
