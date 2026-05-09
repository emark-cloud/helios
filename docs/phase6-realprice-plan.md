# Real P&L on Kite testnet — surgical multi-asset wiring

## Context

Today on Kite testnet, every StrategyVault initializes with `assetUniverse = [mUSDC]` (`contracts/script/DeployPhase1.s.sol:197`). Strategy agents iterate their class-declared universe (`("USDC", "WKITE", "WETH")` for momentum_v1), call the oracle per asset, and try to emit swap calldata — but on chain there is nothing to swap *to*, so trades either fail or no-op and NAV never moves. P&L is structurally synthetic.

The fix is to (1) deploy mock universe tokens, (2) fund `MockSwapRouter` inventory, (3) redeploy all nine StrategyVaults fresh with a multi-asset universe (in-place upgrade is unsafe — `paramsHash` binding would invalidate old proofs), (4) add a small task inside the oracle service that mirrors signed price snapshots into `MockSwapRouter.setPrice(...)` each bar, and (5) fix the one USDC-baked decimal-scaling shortcut in the reference strategies' witness builders. Outcome: strategies trade against real BTC/ETH/SOL prices, swaps execute against synthetic liquidity at those prices, NAV moves with the market, reputation engine consumes real attestations. All on testnet, mainnet stretch path unaffected.

User-confirmed scope: all nine vaults, three new assets (BTC/ETH/SOL), keeper lives inside the oracle service, subgraph redeploys alongside.

## Design summary

| Decision | Choice | Why |
|---|---|---|
| Universe per class | momentum/mean-rev: `[mUSDC, mWBTC, mWETH, mSOL]`; yield-rotation: `[mUSDC]` (carve-out) | Yield-rotation needs yield-bearing wrappers that don't exist on Kite testnet — explicit carve-out per `Helios.md §12.1` (Arbitrum is the yield venue) |
| Vaults | Fresh redeploy of base + Variant2 + Variant3 for all three classes (9 total) | In-place `migrateUniverse` would break paramsHash↔proof binding; fresh redeploy via `RegisterFreshStrategy.s.sol` is ~15 LOC delta and clean |
| Old vaults | Call `StrategyRegistry.deactivate(...)` post-cutover; existing capital exits via normal `defund` | Registry is append-only; deactivate is the supported off-ramp |
| Keeper | New `RouterPriceMirror` task in `services/oracle` subscribed to existing `Poller.on_snapshot` callback | Mirrors `PriceAnchorScheduler` pattern (`services/oracle/src/oracle/service.py:211`); reuses signing + RPC plumbing; no new PM2 entry |
| Decimal handling | `mUSDC=6, mWBTC=8, mWETH=18, mSOL=9`; price converter handles all four | Match real-world decimals so the witness fix is also realistic |
| Mock router fees | 5 bps spread per direction (sell at 9995/10000 of mid) | Avoids unrealistic round-trip arbitrage; small enough not to swamp signal P&L |

## Critical files

### New files
- `contracts/script/DeployTestUniverse.s.sol` — deploys mWBTC (8 dec), mWETH (18 dec), mSOL (9 dec) as `MockERC20` instances; mints generous inventory to deployer; transfers initial inventory into `MockSwapRouter` (target: at least $10M-equivalent of each leg given a $1k demo deposit).
- `contracts/script/DeployPhase6MultiAssetVaults.s.sol` — modeled on `contracts/script/RegisterFreshStrategy.s.sol`. For each of the nine strategies, deploys a fresh UUPS proxy on impl `0x934f7639e5Cb320e4394736f5663b53E9C6b5c7b`, initializes with the per-class universe above, fresh `paramsHash` (`keccak256("helios.<class>.phase6-multiasset-<variant>")`), wires existing TAV (`0x3698…fff81`), oracle anchors, verifier adapters, `allowedRouter = MockSwapRouter`. Registers each in `StrategyRegistry`, restakes operator collateral. Emits a JSON delta written to `kite-testnet.json` under a new `phase6Vaults` block (preserves the legacy entries for explorer continuity).
- `contracts/script/DeactivateLegacyVaults.s.sol` — separate script (kept apart from the redeploy so it can be reverted independently if a regression is found) that calls `StrategyRegistry.deactivate(addr)` on the nine pre-Phase-6 vault addresses.
- `services/oracle/src/oracle/router_mirror.py` — `RouterPriceMirror` class that:
  - Holds a map `{(token_in, token_out): (oracle_asset, decimals_in, decimals_out, side)}`.
  - Receives `on_snapshot(asset, price_e18, ts)` from `Poller` (mirrors the registration in `service.py:232`).
  - Converts `(price_e18, decimals_in, decimals_out)` → `(num, denom)` for both directions using the converter function below.
  - Applies the 5 bps spread per direction.
  - Submits a single `setPrice` tx via the existing `signer` + `web3` plumbing reused from `anchor.py`.
  - Backoff + retry on tx failure; structured-log every successful price update with the asset, leg, and tx hash.
- `services/oracle/src/oracle/router_mirror_math.py` — pure decimal converter `price_e18_to_router_num_denom(price_e18, decimals_in, decimals_out, spread_bps) -> (num, denom)`. Pure function so it gets a focused unit-test table.
- `services/oracle/tests/test_router_mirror_math.py` — unit tests against a fixed table covering BTC ($50k), ETH ($3k), SOL ($150), reverse direction, and decimal-collision cases (in==out, in>out, in<out).
- `services/oracle/tests/test_router_mirror_e2e.py` — integration test that wires `Poller` (with a stub source) → `RouterPriceMirror` → in-process `MockSwapRouter` (Anvil) and asserts `priceOf(...)` reflects the snapshot within one bar.

### Edited files
- `services/oracle/src/oracle/service.py` — instantiate `RouterPriceMirror` alongside `PriceAnchorScheduler` (around line 211); register its `on_snapshot` callback in the existing `Poller` callback list (around line 232). New env vars: `ROUTER_MIRROR_ENABLED` (default off in dev / on in prod), `ROUTER_MIRROR_ADDRESS`, `ROUTER_MIRROR_SIGNER_PK`, `ROUTER_MIRROR_TOKEN_USDC`, `ROUTER_MIRROR_TOKEN_WBTC`, `ROUTER_MIRROR_TOKEN_WETH`, `ROUTER_MIRROR_TOKEN_WSOL`. Default `ORACLE_ASSETS` bumped to `KITE/USDT,BTC/USDT,ETH/USDT,SOL/USDT`.
- `services/oracle/src/oracle/sources/coingecko.py` (or wherever `_COINGECKO_SLUGS` lives — `service.py:114-123`) — add `"SOL/USDT": ("solana", "usd")`. Binance source already covers BTC/ETH; Coingecko is the fallback so SOL only needs the slug entry.
- `reference-strategies/momentum_v1/src/momentum_v1/witness.py` — replace the line 175-179 USDC-only decimal shortcut with a per-asset decimal-aware amount normalizer: take an `asset_decimals: dict[str, int]` parameter (or read from the manifest) and scale `amount_in` / `amount_out` accordingly before composing the witness. Same fix in `reference-strategies/mean_reversion_v1/src/mean_reversion_v1/witness.py`.
- `reference-strategies/momentum_v1/src/momentum_v1/strategy.py:29` — change `asset_universe = ("USDC", "WKITE", "WETH")` to `("USDC", "WBTC", "WETH", "WSOL")`. Same shape change in `mean_reversion_v1/strategy.py:40`. Yield-rotation untouched.
- `reference-strategies/*/tests/` — extend any existing universe-iteration tests to cover the new four-token shape (and the multi-decimal witness path).
- `contracts/deployments/kite-testnet.json` — append `testAssets: { wbtc, weth, wsol }`, `phase6Vaults: { ... 9 addresses }`, and `phase6ParamsHashes: { ... 9 hashes }`. Existing keys stay (for explorer continuity and for the deactivation script to reference).
- `subgraph/subgraph.yaml` — add nine new `dataSources` entries for the Phase-6 vault addresses (mirroring the existing nine entries' structure). Mappings already dispatch by `event.params.strategy`, so `subgraph/src/strategy-vault.ts` does not need code changes.
- `subgraph/networks.json` — append new vault addresses.
- `services/sentinel` and `services/helix` config — update the active-strategy address list to point at the Phase-6 vaults. Per memory, allocators read from the deployment JSON, so this may be a single env-var bump rather than a code change — verify on the day.
- `docs/active-strategies.md` (new, short) — document the Phase-6 cutover: which addresses are live, which are deactivated, and the rationale for the yield-rotation carve-out.
- `scripts/e2e-scenario.sh` — new mode `phase6-realprice` that boots the stack, deposits 1k mUSDC, waits for one allocator cycle, and asserts at least one momentum or mean-reversion strategy NAV moved by an expected sign given the bar's price delta. Fail loudly if NAV stays exactly flat (would indicate the keeper or the witness fix didn't land).

### Deliberately not touched
- `contracts/src/StrategyVault.sol` — no `migrateUniverse` reinitializer. Storage layout and proof binding stay clean.
- `contracts/src/StrategyRegistry.sol` — append-only by design.
- `contracts/src/AllocatorVault.sol` — old allocations to old vaults stay intact; users defund via the existing path.
- `MockSwapRouter.sol` — the contract is already the right shape (rational price, both directions, deadline check). Just feed it.
- Frontend — manifest is read on-chain from the new vault address, so `/strategies/[id]` works once `contracts-abi` deployment JSON is regenerated. Lighthouse + axe regression baselines re-run after redeploy as a checkpoint, not a code change.

## Reused patterns
- `services/oracle/src/oracle/anchor.py` `AnchorPoster.post_async` — copied structurally for `RouterPriceMirror`'s tx submission (signer, RPC, retries).
- `services/oracle/src/oracle/poller.py` `Poller.on_snapshot` callback fan-out — `RouterPriceMirror` registers as a second consumer alongside `PriceAnchorScheduler`.
- `contracts/script/RegisterFreshStrategy.s.sol` — copy + parameterize for the nine-vault redeploy. The existing JSON-merge logic (lines 127-150) handles `kite-testnet.json` updates; no new file plumbing.
- `subgraph/subgraph.yaml` — copy each of the existing nine `dataSources` entries; only `address` and `startBlock` change.

## Verification

1. **Unit tests.** `uv run pytest services/oracle/tests/test_router_mirror_math.py` covers the decimal converter + 5 bps spread across all (in_dec, out_dec) combinations and known prices. Reference-strategy witness tests cover the new decimal-aware path.
2. **Foundry redeploy dry-run.** `forge script DeployTestUniverse --rpc-url $KITE_RPC_URL` and `forge script DeployPhase6MultiAssetVaults --rpc-url $KITE_RPC_URL` against a fork (no `--broadcast`); inspect that the JSON delta is well-formed and addresses look right.
3. **Anvil integration.** `services/oracle/tests/test_router_mirror_e2e.py` boots a local Anvil, deploys `MockSwapRouter`, points `RouterPriceMirror` at a stub source, asserts `priceOf(mUSDC, mWETH)` reflects the next snapshot within one bar (60s default).
4. **Live testnet broadcast.** Run the deploy scripts with `--broadcast` against Kite testnet (chain 2368). Confirm:
   - Nine new vaults registered, nine old vaults deactivated.
   - `MockSwapRouter.priceOf(mUSDC, mWETH)` is non-zero and within 1% of the latest oracle snapshot's `price_e18`.
   - `MockSwapRouter` token balances of mWBTC, mWETH, mSOL, mUSDC are all above the 10M-unit floor.
5. **End-to-end scenario.** `scripts/e2e-scenario.sh phase6-realprice` runs against the live testnet (or a docker-compose stack pointing at it). Pass criteria:
   - Allocator picks ≥ 2 of the new vaults within 90s of deposit.
   - At least one ZK-attested swap (`Swapped` event on `MockSwapRouter`) hits within 3 minutes.
   - One full bar later, `StrategyVault.totalAssets()` differs from the deposited amount in the direction implied by the bar's BTC/ETH/SOL price delta. Tolerance: must move at least 1 bps in the right direction.
6. **Subgraph confirmation.** `pnpm --filter subgraph deploy` (Goldsky); query for `Allocation` and `TradeAttested` events on the new vault addresses; confirm they index correctly.
7. **Lighthouse + axe regression.** Re-run the Phase 4 baselines from `project_phase4_complete.md`. New vault addresses should not regress `/dashboard` or `/strategies` scores; if they do, the cause is likely subgraph propagation lag and not a real regression — note + retest after one Goldsky cycle.

## Risks & mitigations
- **Allocator ranking shifts dramatically once strategies actually move.** Expected; this is the point. Pre-flight: warm up Sentinel against a 1-hour replay of real prices in scenario mode and sanity-check the resulting allocations look stable.
- **Inventory drift in MockSwapRouter under sustained one-side trading.** Initial seed is 10M units per asset; add a small admin-only `topUp` cron in `RouterPriceMirror` (gated by env flag) that mints + transfers more inventory if any leg's balance drops below 1M. Cheap, additive, easy to disable.
- **Old vaults still listed in StrategyRegistry forever.** `DeactivateLegacyVaults.s.sol` flips the registry's active flag so allocators ignore them; existing user capital is reclaimable via the standard defund path.
- **Witness decimal fix could regress the prover.** The change is local to two reference strategies; the prover (`services/prover/src/index.js`) takes a fully-formed witness and is unchanged. New unit tests on the witness builder catch the regression before any on-chain submission.
- **Decimal math is the main bug surface.** Locked down by `test_router_mirror_math.py`'s coverage table and the e2e parity check (oracle `price_e18` ≈ `MockSwapRouter.priceOf`).

## Sequence

1. Land contracts: `DeployTestUniverse.s.sol` + `DeployPhase6MultiAssetVaults.s.sol` + `DeactivateLegacyVaults.s.sol`. Forge dry-run, then broadcast.
2. Land oracle changes: `router_mirror.py` + `router_mirror_math.py` + `service.py` wiring + Coingecko slug + ORACLE_ASSETS bump. Tests pass locally before VPS deploy.
3. Land reference-strategy changes: `witness.py` decimal fix + `strategy.py` universe rewrite. Reference-strategy tests pass.
4. Land subgraph: `subgraph.yaml` + `networks.json` redeploy.
5. Land allocator config: Sentinel + Helix point at Phase-6 vault address list.
6. Run `scripts/e2e-scenario.sh phase6-realprice` against testnet. Triage failures.
7. Tag `v0.6.0-realprice` once the e2e passes twice in a row.

Total estimated effort: ~3-4 days focused. Slots alongside Phase 6 polish; does not block WS8 acceptance.
