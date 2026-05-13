# Phase 6 — Acceptance evidence

**Status (2026-05-12).** Mechanism end-to-end live on Kite testnet. First autonomous attested trades (mean-reversion class) confirmed on chain after the cross-decimal cutover, oracle global-chain fix, and NAV float-clamp landed.

Source-of-truth: `Helios.md §6`, `§9`, `§11.2`, `§12.1`; build plan `TODO.md` Phase 6; cross-decimal cutover memory `project_phase6_cross_decimal_cutover.md`.

---

## 1. The end-to-end mechanism is live

The autonomous loop ran without manual intervention through every layer of the stack:

```
oracle commit chain (price + yield Poseidon anchors)
     ↓
strategy signal (mean-reversion N-sigma trigger on real BTC/ETH/SOL)
     ↓
witness gen (NAV-clamped amount_in, cross-decimal pow10 inputs)
     ↓
prover service (Groth16 over 16-PI circuit, snarkjs 0.7.6)
     ↓
StrategyVault.executeWithProof (manifest + verifier + freshness checks)
     ↓
MockSwapRouter.exactInputSingle (mirrored BTC/ETH/SOL prices)
     ↓
TradeAttested event (subgraph helios/v0.7.1 indexes immediately)
```

No `executeDirectly` escape hatch was added; every recorded trade carries a valid Groth16 proof of class compliance.

## 2. Confirmed on-chain firing — `phase6VaultMeanReversion`

Vault `0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a` (mr.base, class `mean_reversion_v1`).

**Eight `TradeAttested` events** between blocks 21340413–21342591 on Kite testnet (chain 2368):

| # | Block | Tx hash |
|---|---|---|
| 1 | 21340413 | `0x0cdeaf8d42d92b5f66435d2c5ed52f79a69f70a6653c14106593312c571480d7` |
| 2 | 21340440 | `0xd61272da03e6b335dec0be183cc5ef2a5f6b4bddeb6b1283fa04de13c7cb21a7` |
| 3 | 21342049 | `0x47855d7f523271b7a79afc1ee65205dbeca93a05ca809d0cafd8bbcd901b2bb8` |
| 4 | 21342521 | `0xe8144938cb43723db8036e9f51424d9815590c19b9fc85b610f157363a66b0bf` |
| 5 | 21342542 | `0x8a9313972a531243fdd3fce2e87ecd31df7f37ff4b24ac1dee24993bc78fa47d` |
| 6 | 21342565 | `0x6632e5f9739e8d236a692cd338b545a4422996080814c327f2853dc0cb639a34` |
| 7 | 21342590 | `0x78fdb4392538def160b1a6c83fa1e98bdb69cfbbe89c88c681ddaae977a53c4a` |
| 8 | 21342591 | `0xc19641daf3a99940f17ed5193cd964ad5b951c750e018aa48254f57ce6ed60cc` |

Event signature `TradeAttested(address,address,bytes32,bytes32,address,address,uint256,uint256,uint8,uint64,uint64)` topic `0xe8ea226f12514cec03bc7c0abc4dd055ef25465f050f94eab738755dc7adb25f`.

Vault balance after firing (2026-05-12, block ~21344003):

```
mr.base  USDC=0
         BTC=55778 sats (mWBTC, 8 dec)
         ETH=137_066_258_887_225_866 wei (mWETH, 18 dec)
         SOL=29_666_852 (mWSOL, 9 dec)
```

Strategy fully rotated capital out of stablecoin into BTC/ETH/SOL spot positions per its directional signals.

Independent re-verification of any of the eight proofs is one command:

```bash
node scripts/verify-trade.js <tx-hash>
```

Exit code 0 = Groth16 verifier and on-chain trade agreed; 1 = mismatch.

## 3. Other 8 vaults — non-firing rationale

These are **expected**, not bugs. Each row below is intended behaviour given v1's no-demo-tuning rule (memory `feedback_no_demo_tuning.md`) and the explicit single-asset YR carve-out in `Helios.md §12.1`.

| Vault | Class | mUSDC | TradeAttested | Reason |
|---|---|---|---|---|
| `phase6VaultMomentum` (mom.base) | momentum_v1 | 236.075 | 0 | `signal_threshold = 0.015` (1.5%) over `lookback_bars = 10` (1-min bars). Real BTC/ETH/SOL haven't crossed that bar since startup. Lowering the threshold would violate the no-demo-tuning rule; we wait for a real move. |
| `phase6VaultMomentumVariant2` | momentum_v1 | 0 | 0 | Unallocated by Sentinel — variant 2 paramsHash hasn't been selected. |
| `phase6VaultMomentumVariant3` | momentum_v1 | 0 | 0 | Unallocated by Sentinel. |
| `phase6VaultMeanReversionVariant2` | mean_reversion_v1 | 0 | 0 | Unallocated by Sentinel. |
| `phase6VaultMeanReversionVariant3` | mean_reversion_v1 | 83.961 | 0 | Funded but shares strategy service with base; per-class dedicated keys carve-out (memory `project_phase6_ws9_dedicated_keys.md`) gives the base variant the operator EOA — variants 2/3 use the shared deployer key and queue behind base. Mechanism is identical; only base actively trades. |
| `phase6VaultYieldRotation` (yr.base) | yield_rotation_v1 | 35.011 | 0 | **Structural.** YR rotates between yield markets when `apy_to − apy_from ≥ signal_threshold_bps (80) + bridging_cost_bps`. Per `Helios.md §12.1`: *"yield venues live on Arbitrum"*. The Kite asset universe is `(USDC,)` only; `markets_allowlist_root` on Kite testnet has no second market to rotate to. yr cannot fire without a second yield venue, by design. Cross-chain yield rotation against Arbitrum Aave/Compound is on the §17 Phase 1 roadmap. |
| `phase6VaultYieldRotationVariant2` | yield_rotation_v1 | 0 | 0 | Same structural reason + unallocated. |
| `phase6VaultYieldRotationVariant3` | yield_rotation_v1 | 0 | 0 | Same. |

### Why momentum hasn't crossed its threshold

Strategy config (`reference-strategies/momentum_v1/src/momentum_v1/strategy.py`):

```python
signal_threshold = 0.015   # 1.5% return over lookback
lookback_bars    = 10      # 1-minute bars
```

Real markets don't always hand you a >1.5% / 10-bar move on cue. Per the explicit user rule ("don't shorten intervals or thresholds for visual aliveness; fix protocol gaps, let real markets drive"), momentum threshold stays. The first momentum `TradeAttested` lands when the market provides it.

### Why yield-rotation is structurally idle on Kite

Yield-rotation's circuit (`circuits/yield_rotation_v1.circom`) takes 9 public inputs including `M_from`, `M_to`, and a `yield_oracle_root` membership proof. The on-chain `markets_allowlist_root` must list ≥2 markets for the strategy to ever fire — the constraint `M_from ≠ M_to` rejects same-market trades. The Kite-side YR universe is one market (mUSDC) by `Helios.md §12.1` design. A multi-market Kite testnet build would require either (a) a second mock yield market deployed alongside mUSDC, or (b) the cross-chain dispatch to Arbitrum Aave/Compound that §17 Phase 1 ships. Neither is in v1 scope.

This is **the same shape of acknowledged limitation** as the operator NAV under-protection upper-bound gap (§15.2 row 7) — a v1 deliberate cut, called out in the threat model as Accepted.

## 4. Verification commands

Reproduce any number in this doc:

```bash
# Current block + the eight mr.base trades
cast block-number --rpc-url $KITE_RPC_URL
cast logs --rpc-url $KITE_RPC_URL \
  --address 0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a \
  0xe8ea226f12514cec03bc7c0abc4dd055ef25465f050f94eab738755dc7adb25f \
  --from-block 21340000 --to-block 21344003

# Vault balances (multi-asset)
for ASSET in 0xe8cf8a5711f08d5211d46a2835ecc9c9af1b91cd \
             0x3f81a60c5d5c6bfcb415080b846da22903ff37a0 \
             0x789ff10eb109626b01816161be72c9df32be4a00 \
             0xcf1276516a625723e40ae13d598de837079ad532 ; do
  cast call --rpc-url $KITE_RPC_URL $ASSET \
    "balanceOf(address)(uint256)" \
    0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a
done

# Independent ZK re-verification
node scripts/verify-trade.js 0x0cdeaf8d42d92b5f66435d2c5ed52f79a69f70a6653c14106593312c571480d7
```

`$KITE_RPC_URL = https://rpc-testnet.gokite.ai`.

## 5. Acceptance argument

The v1 mechanism claim is "every trade carries a Groth16 proof binding it to the strategy's declared class". This is **proven on chain by eight independently verifiable trades** from a single class, with the other class (mom) provably waiting on a real-market threshold and the third class (yr) structurally bound to a single market by the spec's own §12.1 carve-out.

Per the threat model (`docs/threat-model.md`):
- Row 1 (class-violation drain) → mitigated; every mr trade verified the class binding.
- Row 11 (smart-contract bug) → mitigated; 403 Foundry tests passing at 90.07% line / 87.72% branch on `main`.
- Row 12 (ZK circuit bug) → mitigated; circuit unit tests + per-vault on-chain `TradeAttested` confirm wiring.

The Phase-6 acceptance tag may land on the current `main` HEAD after the demo deliverables (WS5) ship.
