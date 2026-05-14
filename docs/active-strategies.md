# Active strategies — Phase-6 real-price cutover

Source-of-truth list of which StrategyVaults are *active* on Kite
testnet (chain 2368) post-cutover, plus the rationale for the
yield-rotation carve-out.

The chain holds the canonical truth — `StrategyRegistry.active(addr)`
is the gate. This doc records the operator-side intent so a reader
doesn't have to reverse-engineer "why is this address dark."

## Post-cutover active set (nine vaults)

Every active Phase-6 vault runs on impl
`0x934f7639e5Cb320e4394736f5663b53E9C6b5c7b`, references the
redeployed TAV `0x3698f60a…`, and consumes the redeployed oracle
anchors (`OraclePriceAnchor` `0x566e1f1b…`,
`OracleYieldAnchor` `0x345cd375…`). Addresses below are filled in at
WS8 broadcast time.

| Class | Variant | paramsHash seed | Universe |
|---|---|---|---|
| `momentum_v1` | base | `keccak256("helios.mom_v1.phase6.multiasset.base")` | mUSDC, mWBTC, mWETH, mSOL |
| `momentum_v1` | V2 | `…multiasset.v2"` | mUSDC, mWBTC, mWETH, mSOL |
| `momentum_v1` | V3 | `…multiasset.v3"` | mUSDC, mWBTC, mWETH, mSOL |
| `mean_reversion_v1` | base | `keccak256("helios.mr_v1.phase6.multiasset.base")` | mUSDC, mWBTC, mWETH, mSOL |
| `mean_reversion_v1` | V2 | `…multiasset.v2"` | mUSDC, mWBTC, mWETH, mSOL |
| `mean_reversion_v1` | V3 | `…multiasset.v3"` | mUSDC, mWBTC, mWETH, mSOL |
| `yield_rotation_v1` | base | `keccak256("helios.yr_v1.phase6.usdc-only")` | mUSDC only |
| `yield_rotation_v1` | V2 | `…usdc-only.v2"` | mUSDC only |
| `yield_rotation_v1` | V3 | `…usdc-only.v3"` | mUSDC only |

The legacy nine vaults (`strategyVaultMomentum` `0xf11d…`,
`strategyVaultMeanReversion` `0xe85f…`, etc. as listed in
`contracts/deployments/kite-testnet.json`) remain in
`StrategyRegistry` but are flipped to `active=false` by
`contracts/script/DeactivateLegacyVaults.s.sol`. Existing user
capital exits via the standard `defund` path — registry is
append-only by design.

## Why fresh redeploy instead of in-place upgrade

`StrategyVault.executeWithProof` enforces
`publicInputs[PI_PARAMS_HASH] == _activeParamsHash()`. Changing the
asset universe in place requires bumping `paramsHash`, which would
invalidate every queued/in-flight proof bound to the old hash and
break the `keccak256(...)` ↔ proof binding contract. A fresh
ERC1967Proxy avoids this entirely: legacy proofs continue to verify
against the legacy proxy, new proofs target the new proxy, and
ranking flows through the registry's `active` flag.

## Why yield-rotation keeps the single-asset universe

Yield-rotation is the §12.1 yield-venue strategy — it rotates
*between yield-bearing wrappers* (Aave aUSDC, Compound cUSDC, etc.),
not between volatile assets. Kite testnet has no deployed yield
venues, so a multi-asset YR universe would have nothing to rotate
into. The full yield rotation runs on Arbitrum Sepolia (Phase-5
cross-chain leg); the Kite-side YR vault is preserved in the active
set so the §8.2 cohort math sees ≥2 strategies per Poseidon class
(otherwise reputation rank goes degenerate), and so the registry
+ subgraph + frontend filters keep the same shape across all three
classes. Real YR P&L lands via the LayerZero attestation flush from
Arbitrum.

## Operator runbook delta

Both reference allocators (Sentinel + Helix) auto-resolve through
`AllocatorGoldsky.fetch_directory()`'s server-side `where: { active: true }`
filter. No env-var change is required to switch the allocator's
strategy set — it follows the registry.

What *does* change in `/srv/helios/.env` post-broadcast (see
`deploy/env.prod.example` for the full block):

- `MOCK_SWAP_ROUTER_ADDRESS`, `MOMENTUM_STRATEGY_VAULT_ADDRESS`,
  `MEAN_REV_STRATEGY_VAULT_ADDRESS`,
  `YIELD_ROTATION_STRATEGY_VAULT_ADDRESS` populated from the
  `DeployPhase6MultiAssetVaults.s.sol` run-latest.
- `ROUTER_MIRROR_ENABLED=1` plus the four `ROUTER_MIRROR_TOKEN_*`
  legs filled from `DeployTestUniverse.s.sol` run-latest.
- `MOMENTUM_ASSET_DECIMALS_JSON` and `MEAN_REV_ASSET_DECIMALS_JSON`
  set to `{"USDC":18,"WBTC":8,"WETH":18,"WSOL":9}` (or `6` for
  USDC if WS8 redeploys mUSDC at 6 decimals — see
  `deploy/env.prod.example` `ROUTER_MIRROR_USDC_DECIMALS` for the
  same constraint).
- `SENTINEL_CHAIN_WATCH_STRATEGY_VAULTS` set to the comma-joined
  Phase-6 nine so NavDivergenceObserved fan-out reaches subscribed
  users.

## Verification (post-WS8)

1. `cast call $STRATEGY_REGISTRY "active(address)(bool)" $LEGACY_ADDR`
   returns `false` for all nine legacy proxies.
2. `cast call $STRATEGY_REGISTRY "active(address)(bool)" $PHASE6_ADDR`
   returns `true` for all nine Phase-6 proxies.
3. Goldsky `query StrategyDirectory` returns exactly the Phase-6
   nine.
4. `cast call $MOCK_SWAP_ROUTER "priceOf(address,address)((uint256,uint256))" $MUSDC $MWETH`
   returns a non-zero pair within 1% of the latest oracle
   `price_e18` snapshot — confirms the WS2 keeper landed.
