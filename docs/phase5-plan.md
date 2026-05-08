# Phase 5 — Cross-chain implementation plan

> **Source of truth:** `Helios.md §6.9, §12`; `TODO.md` Phase 5 block; `DESIGN.md §10.3`.

## Context

Phase 5 makes Helios cross-chain: strategy agents execute on whichever chain has the right venue for their asset class, while Kite remains the canonical identity / accounting / reputation layer. After Phase 4 (`v0.4.0` tagged 2026-05-07), the spec has anchored on three chains — **Kite testnet (2368)** as canonical, **Base Sepolia (84532)** for deep spot, **Arbitrum Sepolia (421614)** for yield rotation. Mainnet promotion stays a stretch (per CLAUDE.md / TODO.md).

Two scope decisions taken at planning time:

- **Real Uniswap V3 on Base Sepolia, real Aave V3 on Arbitrum Sepolia.** Momentum on Base targets the canonical Uniswap V3 `SwapRouter02` deployment (`0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4`) on Sepolia testnet pools. Yield rotation on Arbitrum Sepolia targets the real Aave V3 `Pool` deployment (`0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff`). V4 is *not* used — testnet support is uneven and the V4 hooks story is a post-hackathon embellishment; V3 is the deepest spot venue with stable Sepolia pools. **Fallback:** the strategy SDK retains a `--router=mock` flag pointing at a deployable `MockSwapRouter` / `MockYieldVault` so a flaky testnet doesn't kill the live demo. Real-router is the default; mock is the safety net, exercised in CI but only invoked in demo if a real-venue health check fails.
- **Per-chain subgraph datasources, single canonical entities keyed by address** (option A — the right shape for v1). Subgraph schema already has `chainId` on `Strategy` and `Trade`. We add Base + Arbitrum datasources to `subgraph.yaml`, drop the `PHASE1_CHAIN_ID = 2368` constant in favour of a per-network resolver, and let entities merge by address (the Kite registry address is the strategy's canonical id). Composite keys would force every frontend query and every Goldsky reader to update; per-chain entities would scatter the "one canonical reputation" logic across consumers. Single-entity keying is the lightest-touch path that still gives us "one strategy, three chains, one reputation."

What's surprising about the starting state — the frontend is mostly already done. `ChainBadge` accepts `pulseKey` + `inFlight`, `/strategies` already has a chain filter UI, `Sunburst` already colours by `chainId`, and `chains.ts` already exports `kiteTestnet`, `baseSepolia`, and `arbitrumSepolia`. Phase 5 frontend work is **wiring real cross-chain events to existing UI**, not building new UI.

What's *not* there:
- `HeliosOApp.sol` (only the interface `contracts/src/interfaces/IHeliosOApp.sol` exists)
- LayerZero V2 lib (remappings in `foundry.toml` point at `lib/layerzero-v2/` which doesn't exist on disk)
- Any Base/Arb deploy script or `deployments/{base,arb}-sepolia.json`
- Per-chain oracle anchors (oracle commits to Kite only today; cross-chain proofs need oracle roots reachable locally for `executeWithProof`)
- Goldsky deployment of the multi-chain manifest

## Architecture in one diagram

```
                       ┌──────────────────────────────┐
                       │  Kite testnet (2368)         │
                       │  CANONICAL                   │
                       │                              │
   reputation ◄────────┤  StrategyRegistry            │
   pulse on            │  AllocatorRegistry           │
   /dashboard          │  ReputationAnchor (V1)       │
                       │  AllocatorVault / UserVault  │
                       │  StrategyVault (mean_rev)    │
                       │  HeliosOApp ◄────┐           │
                       │  OraclePriceAnchor           │
                       └──────────────┬───┴───────────┘
                                      │ LZ V2 messages
                       ┌──────────────┴──────────────┐
                       │                             │
              ┌────────▼─────────┐         ┌─────────▼────────┐
              │ Base Sepolia     │         │ Arbitrum Sepolia │
              │ EXECUTION        │         │ EXECUTION        │
              │                  │         │                  │
              │ StrategyVault    │         │ StrategyVault    │
              │   (momentum_v1)  │         │   (yield_rot_v1) │
              │ TAV + verifiers  │         │ TAV + verifiers  │
              │ HeliosOApp       │         │ HeliosOApp       │
              │ OraclePriceAnchor│         │ OraclePriceAnchor│
              │ Uniswap V3 Router│         │ Aave V3 Pool     │
              │ MockUSDC (OFT)   │         │ MockUSDC (OFT)   │
              └──────────────────┘         └──────────────────┘
```

Capital flow (demo): allocator funds a Base/Arb strategy → `HeliosOApp.bridgeAndDeploy` on Kite → LZ V2 → mints mock USDC into the destination `StrategyVault`. NAV + trade attestation flow: every `executeWithProof` on Base/Arb emits locally → batched by `HeliosOApp` → `_lzReceive` on Kite → `ReputationAnchor.postCrossChainUpdate`.

## Work order

Eight workstreams, ordered by dependency. Each WS targets a sub-branch of `phase-5-cross-chain` and merges into it; the integration branch merges to `main` at the end.

### WS1 — Cross-chain primitives (contracts foundation)

**Branch:** `phase-5-cx-primitives`

- Install LayerZero V2: `forge install layerzerolabs/layerzero-v2 --no-commit`. Confirm `lib/layerzero-v2/` resolves the remappings already in `contracts/foundry.toml:29-30`.
- Implement `contracts/src/HeliosOApp.sol` against `IHeliosOApp` and the LZ V2 `OApp` parent. Concrete shape:
  - State: `mapping(uint32 => mapping(address => uint64)) public lastSeqIn;` for replay protection per (srcEid, srcStrategy).
  - `sendReputationUpdate(uint32 dstEid, address actor, ActorType actorType, ReputationData calldata data, bytes calldata options) external payable` — wraps `_lzSend`.
  - `_lzReceive(...) internal override` — decodes payload, enforces `seq > lastSeqIn[srcEid][actor]`, then calls into `ReputationAnchor.postCrossChainUpdate`. Emits `ReputationMessageReceived`.
  - `bridgeAndDeploy(uint32 dstEid, address strategyOnDst, uint256 amount, bytes calldata options) external payable` — for the demo capital path; pairs with the mock USDC OFT `send` on the source side and a corresponding receiver hook on the destination.
  - `quote(...)` and `setPeer(...)` from the V2 OApp parent.
- Wire payload schemas in a new `contracts/src/lib/CrossChainCodec.sol` so all three chains decode identically. Two payload kinds: `REPUTATION_UPDATE_V1`, `BRIDGE_DEPLOY_V1`.
- Foundry tests in `contracts/test/HeliosOApp.t.sol` using `LayerZeroEndpointMockV2` (ships with the V2 lib): round-trip serialization, replay rejection, peer mis-config, fee quote sanity.

**Critical files:** `contracts/src/HeliosOApp.sol` (new), `contracts/src/lib/CrossChainCodec.sol` (new), `contracts/src/interfaces/IHeliosOApp.sol` (extend with `bridgeAndDeploy` + sequence types), `contracts/src/ReputationAnchor.sol` (already has `setOApp` + `postCrossChainUpdate` — no change needed).

### WS2 — Per-chain contract deployments

**Branch:** `phase-5-cx-deploy` (depends on WS1)

- `contracts/script/DeployBaseSepolia.s.sol`: deploys `StrategyVault` impl, per-class verifiers (`MomentumV1Verifier` + adapter, `MeanReversionV1Verifier` + adapter, `YieldRotationV1Verifier` + adapter), `TradeAttestationVerifier`, `OraclePriceAnchor`, `OracleYieldAnchor`, `HeliosOApp`, `MockUSDC` as an OFT. **Does not** deploy a swap router — Uniswap V3 `SwapRouter02` is already live at `0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4`; the deployment JSON records that address under `swapRouter`. A `MockSwapRouter` is *also* deployed on Base Sepolia under `mockSwapRouter` for the SDK fallback path. Writes `contracts/deployments/base-sepolia.json` matching the shape of `kite-testnet.json`.
- `contracts/script/DeployArbitrumSepolia.s.sol`: same set, no new lending mock — Aave V3 `Pool` is live on Arbitrum Sepolia at `0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff` and is recorded under `aavePool` in the deployment JSON. A small `MockYieldVault` (ERC4626-shape, settable APY) ships under `mockYieldVault` for the SDK fallback path. Writes `contracts/deployments/arbitrum-sepolia.json`.
- `contracts/script/WireLayerZeroPeers.s.sol`: reads all three deployment JSONs, calls `HeliosOApp.setPeer(dstEid, peer)` for each (src, dst) pair. EIDs: Kite = a fresh LZ V2 chain id (check `docs.layerzero.network` — Kite testnet was added 2026-Q1; if missing on testnet, plan B is to register Kite via LZ V2 CLI), Base Sepolia = `40245`, Arb Sepolia = `40231`.
- Mock USDC OFT: use the LZ V2 OFT example (`OFT.sol` parent). Owner mints supply on Kite for the demo capital float; the OFT `send` path moves it to Base/Arb. **Real USDC on testnets is fragmented across faucets and not OFT-wrapped** — using our own MockUSDC OFT keeps the bridge path deterministic without claiming we ship real-USDC capital movement. The trade *destination* (real Uniswap pool, real Aave market) is what makes execution credible; the source-of-funds is admittedly demo-only.
- **Pool / market selection.** Pin to liquid Sepolia pools so trades don't slip catastrophically: Base Sepolia ETH/USDC 0.05%, WBTC/USDC 0.3% (verify pool addresses at deploy time via `UniswapV3Factory.getPool`). Arbitrum Sepolia Aave V3 markets: USDC, USDT, WETH (canonical reserves). Record chosen pool addresses + Aave reserve symbols in the deployment JSON so the SDK reads them, not hardcodes.

**Critical files:** `contracts/script/DeployBaseSepolia.s.sol` (new), `contracts/script/DeployArbitrumSepolia.s.sol` (new), `contracts/script/WireLayerZeroPeers.s.sol` (new), `contracts/src/mocks/MockYieldVault.sol` (new — fallback only), `contracts/src/mocks/MockSwapRouter.sol` (new — fallback only; existing Kite mock can be lifted), `contracts/src/mocks/MockUSDC.sol` (new — OFT extension), `contracts/deployments/base-sepolia.json` (new), `contracts/deployments/arbitrum-sepolia.json` (new). Reuse `contracts/script/DeployPhase3.s.sol` patterns for per-class verifier wiring; don't rewrite that logic.

### WS3 — Per-chain oracle replication

**Branch:** `phase-5-oracle-replication` (parallel with WS2)

Cross-chain proofs validate `oracle_root` against `OraclePriceAnchor.freshness(root)` on the chain where the trade lands. The oracle currently posts only to Kite — strategies on Base/Arb would have no recognised root.

- Extend `services/oracle/` to commit the same Poseidon root to all three anchor contracts each cycle. Single signer key (`ORACLE_SIGNER_PK`) signs the same EIP-712 payload; service writes to all three RPCs. Failure of one chain doesn't stall the others (per-chain commit task).
- Wire `OraclePriceAnchor` and `OracleYieldAnchor` deployments into WS2 deploy scripts.
- Add `ORACLE_BASE_SEPOLIA_RPC` / `ORACLE_ARBITRUM_SEPOLIA_RPC` to `.env.example`.
- Document the failure mode: if oracle hasn't posted to a chain in `MAX_STALENESS_SEC`, `executeWithProof` reverts there — same gate that already exists on Kite.

**Critical files:** `services/oracle/src/oracle/anchor.py` (extend to multi-chain), `services/oracle/src/oracle/config.py` (add per-chain RPC + anchor address resolver), `.env.example`.

### WS4 — Strategy SDK chain-awareness

**Branch:** `phase-5-strategy-sdk-chain` (depends on WS2)

- `packages/strategy-sdk/helios/runtime/config.py`: add `chain: ChainTarget` (enum: `KITE_TESTNET`, `BASE_SEPOLIA`, `ARBITRUM_SEPOLIA`) and `venue: VenueMode` (enum: `REAL`, `MOCK`) to the strategy config. Defaults: `chain=KITE_TESTNET`, `venue=REAL`. Existing Kite strategies still resolve correctly because the Kite deployment JSON already lists the local mock router under both keys.
- `packages/strategy-sdk/helios/runtime/web3_client.py`: resolve RPC + StrategyVault + venue contract from `contracts/deployments/{chain}.json` based on chain target. `venue=REAL` reads `swapRouter` / `aavePool`; `venue=MOCK` reads `mockSwapRouter` / `mockYieldVault`. Same SDK code path; only the target address differs.
- `reference-strategies/momentum_v1/`: add a `build_uniswap_v3_calldata(token_in, token_out, fee, amount_in, min_amount_out, recipient, deadline)` helper alongside the existing Algebra `build_swap_calldata`. UniV3 `exactInputSingle` ABI shape is well-documented (`(address tokenIn, address tokenOut, uint24 fee, address recipient, uint256 deadline, uint256 amountIn, uint256 amountOutMinimum, uint160 sqrtPriceLimitX96)`) — different from Algebra's. Branch on `chain` to choose the helper. Pool fee tiers come from the deployment JSON.
- `reference-strategies/yield_rotation_v1/`: add an Aave V3 adapter (`build_aave_supply_calldata` / `build_aave_withdraw_calldata`). Aave V3 `Pool` ABI: `supply(asset, amount, onBehalfOf, referralCode)` and `withdraw(asset, amount, to)`. Add a thin `aave_apy_view(asset)` helper that reads `Pool.getReserveData(asset).currentLiquidityRate` — the rebalance loop needs cross-protocol rate diffs to make a decision worth attesting to. (Compound V3 is *not* required for v1; the strategy decides between USDC and USDT supply on Aave alone, which is enough for a meaningful rotation event.)
- Mean reversion stays on Kite — no SDK change.
- Tests: extend `packages/strategy-sdk/tests/` with chain-target round-trip tests that assert the right deployment JSON gets read, and golden-file tests for both calldata helpers (the byte-shapes need to match the on-chain ABI exactly so failures show up as test failures, not silent reverts).

**Critical files:** `packages/strategy-sdk/helios/runtime/config.py`, `packages/strategy-sdk/helios/runtime/web3_client.py`, `reference-strategies/momentum_v1/src/momentum_v1/executor.py`, `reference-strategies/yield_rotation_v1/src/yield_rotation_v1/executor.py` (Aave-shape adapter + APY read), `reference-strategies/yield_rotation_v1/src/yield_rotation_v1/aave_v3.py` (new — small adapter module).

### WS5 — Cross-chain trade attestation forwarding

**Branch:** `phase-5-attestation-forward` (depends on WS1, WS2)

- On Base/Arb: extend `StrategyVault.executeWithProof` to call `HeliosOApp.queueAttestation(strategy, attestation)` after local verification. Batched: every N blocks (or when the queue exceeds K entries), `HeliosOApp.flushAttestations(dstEid: KITE_EID, options)` packs the queue into a `REPUTATION_UPDATE_V1` payload and `_lzSend`s.
- On Kite: `_lzReceive` on `HeliosOApp` decodes and calls `ReputationAnchor.postCrossChainUpdate(actor, ActorType.Strategy, data)`. Replay rejection per (srcEid, strategy, seq).
- Reputation engine (`services/reputation/`) already reads from `ReputationAnchor` events — nothing to change there if events fire identically. Confirm `ReputationUpdated` event is emitted from the cross-chain path the same way it is on the off-chain-engine path.
- Anti-spam: cap pending attestations per strategy at `MAX_PENDING = 64`; over-cap reverts `executeWithProof` until flushed.

**Critical files:** `contracts/src/StrategyVault.sol` (add post-verify hook into HeliosOApp on non-Kite chains; gate by `block.chainid != KITE_CHAIN_ID`), `contracts/src/HeliosOApp.sol` (add `queueAttestation` + `flushAttestations`), `services/reputation/src/reputation/anchor.py` (verify cross-chain `ReputationUpdated` events parse identically).

### WS6 — Subgraph multi-chain

**Branch:** `phase-5-subgraph-multichain` (depends on WS2)

- `subgraph/subgraph.yaml`: add Base Sepolia + Arbitrum Sepolia datasources mirroring the existing Kite datasources (StrategyVault, TradeAttestationVerifier, HeliosOApp). Each datasource declares its own `network` and per-chain contract address.
- `subgraph/src/helpers.ts`: replace `PHASE1_CHAIN_ID = 2368` with a `chainIdForNetwork(network: string): i32` lookup. Use `dataSource.network()` everywhere a chain id was hardcoded.
- Confirm Strategy entity merges work: the canonical `Strategy.id` stays the **Kite registry address** (set when the strategy first registers via `StrategyRegistry.RegisterStrategy` on Kite). Trade events on Base/Arb find the same strategy by address. Add a one-line invariant test in `subgraph/tests/` that asserts `Strategy(addr)` is the same row whether populated from a Kite or Base event.
- `subgraph/schema.graphql`: no breaking change. `Trade.chainId` already exists. Add `Strategy.executingChainIds: [Int!]!` (derived/computed) so the dashboard can filter strategies by execution venue without a `Trade` join.
- `pnpm --filter subgraph deploy` once the manifest builds.

**Critical files:** `subgraph/subgraph.yaml`, `subgraph/src/helpers.ts`, `subgraph/src/strategy.ts`, `subgraph/src/tradeAttestationVerifier.ts`, `subgraph/src/heliosOApp.ts` (new mapping for cross-chain message events).

### WS7 — Frontend wiring

**Branch:** `phase-5-fe-wiring` (depends on WS6)

Most UI is already in place from Phase 4. Phase 5 = wire real events to it.

- `frontend/src/lib/sentinelStream/`: emit `CROSS_CHAIN_REP_UPDATE_INFLIGHT` (when `HeliosOApp.ReputationMessageSent` fires on Base/Arb) and `CROSS_CHAIN_REP_UPDATE_RESOLVED` (when matching `ReputationMessageReceived` fires on Kite). Match by GUID.
- `frontend/src/components/atoms/ChainBadge.tsx`: drive `inFlight={true}` from a strategy's pending GUID set; drive `pulseKey` from the resolved event's blockNumber. Both props already exist — just need a real source.
- `frontend/src/components/dashboard/ActivityRail.tsx`: render new event kinds. Reuse the existing event-row component; new copy in `frontend/src/lib/copy/events.ts`.
- `frontend/src/lib/chains.ts`: confirm `SUPPORTED_CHAINS` covers all three (already does); add `BASE_SEPOLIA_RPC_URL` / `ARBITRUM_SEPOLIA_RPC_URL` env wiring with viem fallback.
- `frontend/src/lib/format.ts:158-162`: explorer URLs already mapped; verify after deployment.
- `/strategies` chain filter: already wired to `row.chainId` — no code change, but visual QA against three-chain data.

**Critical files:** `frontend/src/lib/sentinelStream/sources.ts`, `frontend/src/components/dashboard/ActivityRail.tsx`, `frontend/src/lib/chains.ts`, `frontend/src/lib/copy/events.ts`. **Do not** rebuild any Phase-4-complete component.

### WS8 — End-to-end + acceptance

**Branch:** `phase-5-acceptance` (depends on all prior WS)

- Extend `scripts/e2e-scenario.sh` to run against the deployed testnets (preferred per the *test against the real product* memory). One strategy per chain: mean-reversion on Kite (Algebra), momentum on Base (real Uniswap V3), yield-rotation on Arbitrum (real Aave V3). One CI variant runs `venue=MOCK` so test correctness doesn't depend on testnet liquidity; the demo runbook runs `venue=REAL`.
- Pre-demo health checks (`scripts/preflight-phase5.sh`): for each pool/market the demo touches, query reserves / liquidity / `currentLiquidityRate` and assert minimum thresholds. If any threshold fails, the runbook flips that strategy to `venue=MOCK` for the demo. This is the documented escape hatch from the "real testnet flakes" risk — it must exist before we tag `v0.5.0`.
- Allocator decision test (`services/sentinel/tests/test_phase5_xchain.py`): cross-chain reputation ticks must produce a measurably different allocation in the next rebalance versus a control where the cross-chain delta is suppressed. This is the spec's "measurable effect on Sentinel/Helix allocation decisions" acceptance row. Runs in `venue=MOCK` so the test isn't flaky.
- Demo timing test: profitable Arb trade → Kite reputation tick within 30–60s on default LZ DVN config.
- `docs/phase5-acceptance.md` written when the acceptance suite is green; mirror the format of `docs/phase4-acceptance.md`.

**Critical files:** `scripts/e2e-scenario.sh`, `services/sentinel/tests/test_phase5_xchain.py`, `docs/phase5-acceptance.md` (new).

## Sequencing summary

| Order | WS | Depends on | Notes |
|---|---|---|---|
| 1 | WS1 — primitives | — | Unblocks everything else |
| 2a | WS2 — deploys | WS1 | Run alongside WS3 |
| 2b | WS3 — oracle replication | WS1 | No contract dep — can start as soon as WS2 mocks compile |
| 3 | WS4 — SDK chain-awareness | WS2 | Needs deployment JSONs |
| 4 | WS5 — attestation forwarding | WS1, WS2 | Real LZ traffic begins here |
| 5 | WS6 — subgraph multi-chain | WS2 | Needs deployed addresses |
| 6 | WS7 — frontend wiring | WS6 | Wire real events to existing UI |
| 7 | WS8 — acceptance + e2e | all | Ships `v0.5.0` tag |

## Reuse — explicit list of existing utilities

These already exist; do not reimplement. Cited so the work order isn't ambiguous.

- `contracts/script/DeployPhase3.s.sol` — patterns for verifier-adapter wiring, registry posts, JSON merge into `deployments/*.json`. Mirror its structure in `DeployBaseSepolia.s.sol` / `DeployArbitrumSepolia.s.sol`.
- `contracts/src/ReputationAnchor.sol` — `setOApp`, `onlyOApp` modifier, `postCrossChainUpdate` already exist. Just point at the new HeliosOApp address.
- `contracts/src/StrategyVault.sol` — `executeWithProof` is the post-verify hook point. Wrap, don't fork.
- `subgraph/subgraph.yaml:36-37` — explicit Phase 5 comment naming the datasources to add.
- `frontend/src/components/atoms/ChainBadge.tsx` — `pulseKey` + `inFlight` props already plumbed.
- `frontend/src/components/strategies/StrategiesFilters.tsx:51-61` — chain filter chips already render Kite/Base/Arb.
- `frontend/src/components/sunburst/Sunburst.tsx:158-164` — chain colours already wired via CSS variables.
- `frontend/src/lib/chains.ts` — `kiteTestnet`, `baseSepolia`, `arbitrumSepolia` already exported.
- `frontend/src/styles/tokens.css:88-91` — `--chain-kite`, `--chain-base`, `--chain-arbitrum` already defined.
- `services/sentinel/` and `services/helix/` — both already read reputation from on-chain events; no allocator-side change required if `ReputationUpdated` fires identically from the cross-chain path.

## Verification — end-to-end demo path

After all eight workstreams land:

1. Deploy: `forge script DeployBaseSepolia.s.sol --broadcast --rpc-url base_sepolia` then the same for Arb, then `WireLayerZeroPeers.s.sol`. Verify `contracts/deployments/{base,arbitrum}-sepolia.json` populated, and that `swapRouter` / `aavePool` addresses match the canonical Uniswap V3 / Aave V3 deployments.
1a. Run `scripts/preflight-phase5.sh` — confirms real-venue health on Base + Arb. If any pool fails, flip that strategy to `venue=MOCK` for the demo run.
2. Oracle: `python -m services.oracle` — confirm in logs that all three anchor commits succeed each cycle.
3. Subgraph: `pnpm --filter subgraph deploy`; in Goldsky logs, watch indexing progress on three networks; query `Strategy(id: <kite-addr>)` and confirm trades from Base appear in the trade subset.
4. Strategies: deploy momentum on Base + yield-rotation on Arb via `helios deploy --chain base-sepolia` / `--chain arbitrum-sepolia`. Confirm a trade lands locally, the local TAV verifies, and a `ReputationMessageSent` event fires on the source chain.
5. Wait 30–60s; observe `ReputationMessageReceived` on Kite + `ReputationUpdated` on the canonical anchor.
6. Frontend `/dashboard`: chain badge pulses on the strategy row, in-flight clock dot resolves to the new score, activity rail renders `CROSS_CHAIN_REP_UPDATE_INFLIGHT → RESOLVED` pair.
7. Run `services/sentinel/tests/test_phase5_xchain.py` — allocator measurably re-allocates after the cross-chain tick.
8. Run `scripts/e2e-scenario.sh` — full three-chain scenario green.

When all eight pass, tag `v0.5.0`, write `docs/phase5-acceptance.md`, update `TODO.md` Phase 5 block to checked, and Phase 6 (polish + submission) becomes current.
