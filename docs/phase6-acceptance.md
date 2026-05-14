# Phase 6 — Acceptance evidence

**Status (2026-05-14).** Mechanism end-to-end live on **three chains** —
Kite testnet (autonomous attested trades) plus Base Sepolia and Arbitrum
Sepolia (cross-chain capital routing via LayerZero V2). Today's bring-up
closed the §12.1 venue-routing path: the sentinel allocator fired three
real `RemoteAllocationSent` messages, LZ V2 delivered each, and the
destination strategy vaults now hold real on-chain capital.

Source-of-truth: `Helios.md §6`, `§9`, `§11.2`, `§12.1`; build plan `TODO.md`
Phase 6; cross-decimal cutover memory `project_phase6_cross_decimal_cutover.md`;
cross-chain bring-up memory `project_cxr0c_kite_faucet_blocker.md`;
cost-optimization roadmap `docs/cross-chain-cost-roadmap.md`.

---

## 1. The end-to-end mechanism is live

### 1.1 Local trade flow (Kite-side)

The autonomous loop runs without manual intervention through every layer
of the local stack:

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
TradeAttested event (subgraph helios/v0.9.0 indexes immediately)
```

No `executeDirectly` escape hatch was added; every recorded trade
carries a valid Groth16 proof of class compliance.

### 1.2 Cross-chain allocation flow (§12.1 venue routing)

When the sentinel allocator chooses a remote strategy (mom/mr on Base
for deep liquidity, yr on Arb for Aave-shaped lending venues), capital
moves cross-chain via LayerZero V2 OFT + composeMsg:

```
sentinel diff → AllocatorVault.allocateToRemoteStrategy(...)
     ↓
UserVault → AllocatorVault custody transfer (Kite-local)
     ↓
mUSDC OFT adapter (Kite) → LZ Endpoint
     ↓ (LZ V2 message + composeMsg, ~1.0–1.1 KITE fee)
mUSDC OFT adapter (Base/Arb) → release mUSDC
     ↓
HeliosBridgeReceiver.lzCompose → StrategyVault.onCrossChainAllocate
     ↓
CrossChainAllocateExecuted event (Base/Arb subgraph indexes)
```

Both `_lzReceive` (token release) and `lzCompose` (dispatch) execute
on the destination chain; either failure routes funds to the per-user
`recoverable[user]` parked-balance pattern (zero recoverable balance
on any chain at this writing).

---

## 2. Confirmed on-chain firing — multi-chain evidence

### 2.1 `phase6VaultMeanReversion` (mr.kite) — eight attested trades

Vault `0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a` on Kite testnet,
class `mean_reversion_v1`.

**Eight `TradeAttested` events** between blocks 21340413–21342591:

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

Event signature `TradeAttested(address,address,bytes32,bytes32,address,address,uint256,uint256,uint8,uint64,uint64)` topic
`0xe8ea226f12514cec03bc7c0abc4dd055ef25465f050f94eab738755dc7adb25f`.

Multi-asset balance after firing:

```
mr.kite  USDC = 0
         BTC  = 55_778 sats (mWBTC, 8 dec)
         ETH  = 137_066_258_887_225_866 wei (mWETH, 18 dec)
         SOL  = 29_666_852 (mWSOL, 9 dec)
```

The strategy fully rotated capital out of stablecoin into BTC/ETH/SOL
spot positions per its directional signals.

Independent re-verification of any of the eight proofs is one command:

```bash
node scripts/verify-trade.js <tx-hash>
```

Exit code 0 = Groth16 verifier and on-chain trade agreed; 1 = mismatch.

### 2.2 Cross-chain allocation — three real LZ V2 hops

The §12.1 capital-routing path went live 2026-05-14 12:01–12:02Z. The
sentinel allocator's first post-fund cold-start fired three real
`OFT.send` transactions from Kite, each carrying a composeMsg that
dispatched a `StrategyVault.onCrossChainAllocate` on the destination.

| Strategy | Dst chain | dstEid | Kite tx | Amount |
|---|---|---|---|---|
| `mr.base`  `0x8b375617…` | Base Sepolia | 40245 | `0x6ef584a1d4100eec78f3d8525b85c5f3486ea1627accfdab7d9996b091870862` | 0.650331 mUSDC |
| `mom.base` `0x9e14299e…` | Base Sepolia | 40245 | `0xfee792dce6e8da7b5557baf464fecdfd83a565a784f84df2becff98ae0814a3c` | 0.650331 mUSDC |
| `yr.arb`   `0x516f23b9…` | Arb Sepolia  | 40231 | `0xcda2e6bdabea44eb10d1cf57d3b00101847d57c476d0be1b14dadb265f8fd733` | 0.650331 mUSDC |

Each tx emits the full pipeline:
`UserVault→AllocatorVault Transfer` → AllocatorVault custody-decrement →
OFT adapter approval + transfer → LZ Endpoint `PacketSent` →
OFT adapter `OFTSent` → AllocatorVault `RemoteAllocationSent`
(topic `0xde843aa6…`).

Destination-chain credit confirmed via direct balance read (mUSDC is
6-dec on Base/Arb, so the OFT `_removeDust` floors 0.650331347… × 10¹⁸
wei to 650_331 base units):

```
mom.base StrategyVault mUSDC = 650_331       (Base Sepolia 84532)
mr.base  StrategyVault mUSDC = 650_331       (Base Sepolia 84532)
yr.arb   StrategyVault mUSDC = 650_331       (Arb  Sepolia 421614)
Base BridgeReceiver mUSDC    = 0             (no parked funds)
Arb  BridgeReceiver mUSDC    = 0             (no parked funds)
```

Zero parked balance on either BridgeReceiver means `lzCompose` ran
cleanly on every leg — `onCrossChainAllocate` did not revert.

LZScan traces:
- https://testnet.layerzeroscan.com/tx/0x6ef584a1d4100eec78f3d8525b85c5f3486ea1627accfdab7d9996b091870862
- https://testnet.layerzeroscan.com/tx/0xfee792dce6e8da7b5557baf464fecdfd83a565a784f84df2becff98ae0814a3c
- https://testnet.layerzeroscan.com/tx/0xcda2e6bdabea44eb10d1cf57d3b00101847d57c476d0be1b14dadb265f8fd733

---

## 3. Cross-chain cost optimization (Tier 1 + Tier 2)

Empirical LZ V2 testnet fee on Kite: **~1.08 KITE per `OFT.send`**
regardless of payload size — mostly fixed-cost (DVN floor + executor
base fee), not gas-driven. Per `docs/cross-chain-cost-roadmap.md`, two
levers shipped in Phase 6 polish:

| Lever | Default | Effect |
|---|---|---|
| **Tier 1 — threshold gate** `SENTINEL_MIN_CROSS_CHAIN_ALLOC_USD_WEI` | `10e18` ($10) | Skip sub-threshold dust cross-chain ops; let delta accumulate over ticks. |
| **Tier 1 — flush cadence** `SENTINEL_CROSS_CHAIN_FLUSH_CADENCE_SEC` | `300` (5 min) | Per-(user, strategyId) cooldown; suppress per-tick re-fires within window. |
| **Tier 2 — batched compose** `AllocatorVault.allocateToRemoteStrategyBatch` | (always) | Pack N same-destination strategies into 1 OFT.send; LZ fee amortized. |

**Verified on-chain.** Tier 1 threshold_skip fired live on 0.16 mUSDC
ops on the 12:15:31Z tick — three would-be sends suppressed silently,
preserving the sentinel allocator EOA's KITE balance. Tier 2 batch
path is deployed (`allocatorVaultImplBatch` =
`0xe7b8540BaEb9c502bc6D2c4FF3114a20B8476474` via UUPS upgrade) and
unit-tested in Foundry; on-chain batched submission will be observed
on the first cold-start where two same-destination ops each exceed
$10.

Subgraph `helios/v0.9.0` ships the `CrossChainAllocation` entity to
let consumers group by `txHash` for empirical batch-size measurement.

---

## 4. Non-firing rationale — refreshed

The Kite-side cohort and the Base/Arb cohort have different reasons
for not yet emitting `TradeAttested` events. Each row is **expected**,
not a bug.

### 4.1 Kite-side cohort

| Vault | Class | mUSDC | TradeAttested | Reason |
|---|---|---|---|---|
| `phase6VaultMomentum` (mom.kite) | momentum_v1 | 236.075 | 0 | `signal_threshold = 0.015` (1.5%) over `lookback_bars = 10` (1-min bars). Real BTC/ETH/SOL haven't crossed that bar since startup. The no-demo-tuning rule prevents lowering it — we wait for a real move. |
| `phase6VaultMomentumVariant2` | momentum_v1 | 0 | 0 | Variant 2 paramsHash not selected by sentinel. |
| `phase6VaultMomentumVariant3` | momentum_v1 | 0 | 0 | Same — unselected variant. |
| `phase6VaultMeanReversionVariant2` | mean_reversion_v1 | 0 | 0 | Unselected variant. |
| `phase6VaultMeanReversionVariant3` | mean_reversion_v1 | 83.961 | 0 | Funded, but shares the strategy service with `mr.kite` base; per-class dedicated keys carve-out gives base the operator EOA — variants 2/3 queue behind. |
| `phase6VaultYieldRotation` (yr.kite) | yield_rotation_v1 | 35.011 | 0 | The Kite asset universe is `(USDC,)` only; `markets_allowlist_root` on Kite covers `aave-v3:USDC, aave-v3:USDT` but the on-Kite venue is a single mock — yr requires `M_from ≠ M_to` and `apy_to − apy_from ≥ threshold` on a real venue diff, which Kite does not expose. The yr signal fires on Arb, not Kite — see 4.2 below. |
| `phase6VaultYieldRotationVariant2` | yield_rotation_v1 | 0 | 0 | Same structural reason + unselected. |
| `phase6VaultYieldRotationVariant3` | yield_rotation_v1 | 0 | 0 | Same. |

### 4.2 Cross-chain cohort

| Vault | Chain | mUSDC | TradeAttested | Reason |
|---|---|---|---|---|
| `phase6VaultMomentumBase` (mom.base) `0x9e14299e…` | Base Sepolia | 0.650331 | 0 | Capital landed at 12:01:58Z. Strategy lookback window (`lookback_bars = 10`) hasn't yet refilled with venue-local price snapshots, and the signal still needs a >1.5% directional move to fire. |
| `phase6VaultMeanReversionBase` (mr.base) `0x8b375617…` | Base Sepolia | 0.650331 | 0 | Capital landed at 12:01:56Z. Same lookback-fill condition; mr's N-σ trigger fires on observed volatility, not synthetic mirror data. |
| `phase6VaultYieldRotationArb` (yr.arb) `0x516f23b9…` | Arb Sepolia | 0.650331 | 0 | Capital landed at 12:02:00Z. `allowedRouter` is a `MockYieldVault` (Aave-V3-shaped) because the Aave Sepolia FiatToken USDC faucet is admin-gated; the rotation signal fires when the mock venue's APY crosses the second market by `signal_threshold_bps (80) + bridging_cost_bps (30)`. Wiring is one `setAllowedRouter` call from real Aave once Aave's Sepolia faucet opens. |

The cross-chain cohort's capital arrived ~5 minutes before this
writeup — none has accumulated enough venue-local price history for
its signal to fire. This is normal; the local mr.kite vault's first
`TradeAttested` landed ~30 minutes after capital first arrived under
the same lookback rule.

---

## 5. Verification commands

Reproduce any number in this doc. `$KITE_RPC_URL =
https://rpc-testnet.gokite.ai`, plus `BASE_SEPOLIA_RPC_URL` /
`ARBITRUM_SEPOLIA_RPC_URL` from `.env.example`.

```bash
# Eight mr.kite TradeAttested events
cast logs --rpc-url $KITE_RPC_URL \
  --address 0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a \
  0xe8ea226f12514cec03bc7c0abc4dd055ef25465f050f94eab738755dc7adb25f \
  --from-block 21340000 --to-block 21344003

# mr.kite multi-asset balance
for ASSET in 0xe8cf8a5711f08d5211d46a2835ecc9c9af1b91cd \
             0x3f81a60c5d5c6bfcb415080b846da22903ff37a0 \
             0x789ff10eb109626b01816161be72c9df32be4a00 \
             0xcf1276516a625723e40ae13d598de837079ad532 ; do
  cast call --rpc-url $KITE_RPC_URL $ASSET \
    "balanceOf(address)(uint256)" \
    0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a
done

# Independent ZK re-verification
node scripts/verify-trade.js \
  0x0cdeaf8d42d92b5f66435d2c5ed52f79a69f70a6653c14106593312c571480d7

# Three RemoteAllocationSent events on Kite AllocatorVault
cast logs --rpc-url $KITE_RPC_URL \
  --address 0xf3e4452fe17edbfa6833022b9c186aa14b98955d \
  $(cast keccak "RemoteAllocationSent(address,bytes32,uint32,address,uint256)") \
  --from-block 21392010

# Destination-chain credit (mUSDC at the venue address)
cast call --rpc-url $BASE_SEPOLIA_RPC_URL \
  0xe8CF8A5711F08D5211d46a2835EcC9C9af1B91Cd \
  "balanceOf(address)(uint256)" 0x9e14299e6FAeE1C1F352E2F9197D8A080306FE8d  # mom.base
cast call --rpc-url $BASE_SEPOLIA_RPC_URL \
  0xe8CF8A5711F08D5211d46a2835EcC9C9af1B91Cd \
  "balanceOf(address)(uint256)" 0x8b375617589DBC7A90049b0fE07f2Fb4D5A19F08  # mr.base
cast call --rpc-url $ARBITRUM_SEPOLIA_RPC_URL \
  0xe8CF8A5711F08D5211d46a2835EcC9C9af1B91Cd \
  "balanceOf(address)(uint256)" 0x516f23B9d2b6918D005d00Ccea3074cED1f8D005  # yr.arb
```

---

## 6. Acceptance argument

The v1 mechanism claim is "every trade carries a Groth16 proof binding
it to the strategy's declared class, and capital flows autonomously
across chains under the user's signed meta-strategy". Both halves are
**proven on chain**:

- **ZK class binding** — eight independently verifiable mean-reversion
  trades on mr.kite (`scripts/verify-trade.js` exits 0 against each).
- **Autonomous cross-chain routing** — three real
  `RemoteAllocationSent` messages from sentinel's allocator loop,
  delivered via LayerZero V2, credited to the destination
  StrategyVaults under their canonical operator/navOracle keys.
- **Cost-controlled at scale** — Tier 1 threshold gate suppresses
  dust-tier LZ V2 sends; Tier 2 batched compose is on-chain and ready
  for multi-strategy ticks.

Per the threat model (`docs/threat-model.md`):
- Row 1 (class-violation drain) → mitigated; every mr trade verified
  the class binding.
- Row 11 (smart-contract bug) → mitigated; 403 Foundry tests passing
  at 90.07% line / 87.72% branch on `main`.
- Row 12 (ZK circuit bug) → mitigated; circuit unit tests + per-vault
  on-chain `TradeAttested` confirm wiring.
- §12.1 cross-chain routing → no longer a "deliberate v1 cut"; live
  on Base + Arb testnets with real LZ V2 messages.

The Phase-6 acceptance tag (`v0.5.0`) may land on the current `main`
HEAD (`41619ab`) after the demo deliverables (WS5) ship.
