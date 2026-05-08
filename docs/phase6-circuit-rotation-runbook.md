# Phase 6 — `momentum_v1` + `mean_reversion_v1` verifier rotation runbook

## Context

`circuits/momentum_v1.circom` and `circuits/mean_reversion_v1.circom` were edited 2026-05-08 to add **Constraint 0: `amount_in > 0`** — a `Num2Bits(128)` positivity check on `amount_in - 1`, mirroring `yield_rotation_v1.circom:209-214`'s Constraint 7. This closes a gap surfaced during Phase 6 circuit-test work where `amount_in = 0` passed witness generation despite producing a no-op trade.

`yield_rotation_v1` is **not** rotated — its Constraint 7 already enforces the equivalent positivity check; circuit + verifier address are unchanged.

## Repo-side state (already landed)

- Circuits edited (Constraint 0 added). Constraint counts: momentum_v1 7268 → 7396 (+128), mean_reversion_v1 7251 → 7379 (+128). Both well under the 20k budget.
- Artifacts regenerated: `.r1cs`, `.wasm`, `.zkey`, `Solidity Verifier` for both classes (`circuits/build/<class>/`, `contracts/src/verifiers/{Momentum,MeanReversion}V1Verifier.sol`).
- Forge fixtures regenerated: `contracts/test/fixtures/{momentum,mean_reversion}_v1.json`.
- Tests added: `amount_in == 0 rejected` in both `circuits/test/<class>.test.js`. 43/43 circuit tests pass.
- Forge: 390/391 tests pass (1 pre-existing skip).
- Prover: 10/10 tests pass against the new artifacts.
- Docs updated: `docs/circuit-specs.md` reflects new constraint counts + drops the old "TODO" zero-amount gap notes.

## Chain-side state (pending broadcast)

`TradeAttestationVerifier.CHANGE_DELAY = 2 days` (`contracts/src/TradeAttestationVerifier.sol:32`). Two Foundry scripts handle the timelocked rotation:

- **`contracts/script/ProposeVerifierRotation.s.sol`** — deploys new verifier + adapter for momentum_v1 and mean_reversion_v1, calls `proposeVerifierChange` for both class IDs.
- **`contracts/script/CommitVerifierRotation.s.sol`** — runs after `T + 2 days`. Calls `commitVerifierChange` for both class IDs and patches `contracts/deployments/kite-testnet.json` with the new addresses.

## Step 1 — Propose (today, T0)

```bash
cd contracts
DEPLOYER_PK=0x...                             # TAV owner key
TRADE_VERIFIER=0x743e1bd7e9795e78b10965eaeaa93bf215476c96  # current TAV on Kite testnet

forge script script/ProposeVerifierRotation.s.sol \
  --rpc-url https://rpc-testnet.gokite.ai \
  --broadcast \
  --slow
```

Expected logs (capture these — needed for Step 2):

```
=== verifier-rotation propose ===
chainId:                         2368
MomentumV1Verifier (new):        0x...
MomentumV1VerifierAdapter (new): 0x...   ← class map will commit to this
MeanReversionV1Verifier (new):   0x...
MeanReversionV1VerifierAdapter:  0x...   ← class map will commit to this
commit eta (unix):               <T0 + 172800>
```

Stash the four addresses + the eta; you'll feed them back to the commit script.

After this lands:
- `verifierByClassMap[momentum_v1]` and `verifierByClassMap[mean_reversion_v1]` still point at the **old** adapters. Existing strategies + sentinel + prover keep working unchanged.
- Anyone reading `tav.proposedVerifier(<classId>)` (if such a getter exists; otherwise the storage slot) will see the new adapter address pending commit.

## Step 2 — Wait

T0 + 48h. Earliest commit time is `block.timestamp >= proposedAt + 2 days`. `commitVerifierChange` reverts via `ChangeNotReady` if invoked early — safe to call speculatively.

Demo deadline 2026-05-18 — comfortable runway.

## Step 3 — Commit (T0 + 2 days)

```bash
cd contracts
DEPLOYER_PK=0x...
TRADE_VERIFIER=0x743e1bd7e9795e78b10965eaeaa93bf215476c96
MOMENTUM_VERIFIER_NEW=0x...                   # from Step 1 log
MOMENTUM_VERIFIER_ADAPTER_NEW=0x...           # from Step 1 log
MEAN_REVERSION_VERIFIER_NEW=0x...             # from Step 1 log
MEAN_REVERSION_VERIFIER_ADAPTER_NEW=0x...     # from Step 1 log

forge script script/CommitVerifierRotation.s.sol \
  --rpc-url https://rpc-testnet.gokite.ai \
  --broadcast \
  --slow
```

The script asserts `verifierByClassMap` matches the expected adapters before patching JSON, so a mismatched env var will revert before the file write.

Expected logs:

```
=== verifier-rotation commit ===
chainId:                  2368
verifierByClassMap[mom]:  0x...   ← matches MOMENTUM_VERIFIER_ADAPTER_NEW
verifierByClassMap[mr]:   0x...   ← matches MEAN_REVERSION_VERIFIER_ADAPTER_NEW
merged into:              ./deployments/kite-testnet.json
```

## Step 4 — Post-commit

After the JSON patch lands:

1. **Verify the rotation**:
   ```bash
   cast call $TRADE_VERIFIER "verifierByClassMap(bytes32)(address)" \
     0x9b1d5c6cd5af3acb5d3a44b5f5faa6a8d50b4d20a9b9d8d5c5b5a5f5d5e5b5c5  # CLASS_MOM
   ```
2. **Update `CLAUDE.md`** "Key addresses" block — bump the `momentum_v1` and `mean_reversion_v1` verifier-adapter pins (raw verifier addresses too).
3. **Smoke-test end-to-end** by running the demo scenario or a single `executeWithProof` call against a strategy. The new circuit's Constraint 0 now enforces `amount_in > 0` on-chain.
4. **Optionally**: propose `setMeta` calls on `StrategyVault*` to bump `paramsHash` if the rotation's intent is to also signal a strategy-config change (not required — the params themselves haven't changed, only the verifier).

## Rollback (only if commit fails or the new circuit misbehaves)

The 2-day timelock means the old verifier remains active throughout the wait. If something looks wrong post-propose:

- **Within the 2 days**: simply do not commit. The propose slot expires implicitly (a fresh `proposeVerifierChange` overwrites the pending slot).
- **After commit**: re-deploy the old verifier address (its source is still in git history) and propose a rotation back. Same 2-day delay applies.

## Why no `yield_rotation_v1` rotation

`circuits/yield_rotation_v1.circom` lines 207-214 already enforce `amount_rotating > 0` via the same `Num2Bits(128)` pattern. Circuit untouched, .zkey untouched, verifier address untouched.
