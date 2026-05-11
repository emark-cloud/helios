# Post-demo TAV restore — bring back the 2-day verifier-change timelock

## Background

The on-chain `TradeAttestationVerifier` (TAV) gates which Groth16 verifier
each strategy class points at. The production posture is a 2-day
propose/commit timelock on `proposeVerifierChange` →
`commitVerifierChange` so an owner-key compromise cannot swap in a
malicious verifier instantly.

For the Phase-6 hackathon demo we needed to ship the
bit-widened (Num2Bits 64 → 96) momentum + mean-reversion verifiers in
under a day. The 48h window between propose and commit was too long, so:

- `contracts/src/TradeAttestationVerifier.sol` was edited to
  `uint256 public constant CHANGE_DELAY = 0;` (with a TEMPORARY comment).
- A fresh TAV was deployed with this constant and the new verifier
  addresses registered in one shot via `registerVerifier` (rather than
  going through propose/commit).
- Each Phase-6 strategy vault was UUPS-upgraded to a new
  `StrategyVault` impl that exposes `migrateVerifier(address) external
  onlyOwner reinitializer(2)`, and the migrate consumed
  `reinitializer` slot 2.

This document is the playbook for restoring the 2-day delay after the
demo is recorded and the submission window closes.

## What changed on-chain during the demo period

- **TAV address on `kite-testnet.json`** points at the new no-timelock
  contract (see `contracts/deployments/kite-testnet.json` →
  `addresses.tradeAttestationVerifier`).
- **All 9 phase-6 strategy vaults' `tradeAttestationVerifier` field**
  was overwritten to the new TAV via `migrateVerifier(newTAV)`. The
  vault proxies are otherwise unchanged.
- **Verifier addresses** (`momentumVerifierAdapter`,
  `meanReversionVerifierAdapter`) point at the Path-B bit-widened
  contracts. These addresses are good — no further redeploy needed.
- **`reinitializer(2)`** is consumed on every vault proxy. The next
  re-init MUST use `reinitializer(3)`.

## The restore — three small source edits + one broadcast

### 1. Revert `CHANGE_DELAY` to the production value

In `contracts/src/TradeAttestationVerifier.sol`, change the constant
back:

```solidity
// Was: uint256 public constant CHANGE_DELAY = 0;  // hackathon-window override
uint256 public constant CHANGE_DELAY = 2 days;
```

Drop the TEMPORARY comment block. Keep the propose/commit machinery as
is — it's already correct for `CHANGE_DELAY > 0`.

### 2. Bump `StrategyVault.migrateVerifier` to `reinitializer(3)`

In `contracts/src/StrategyVault.sol`, the existing line is:

```solidity
function migrateVerifier(address newVerifier) external onlyOwner reinitializer(2) {
```

Change to:

```solidity
function migrateVerifier(address newVerifier) external onlyOwner reinitializer(3) {
```

Update the surrounding comment block to record that slot 2 was burned
by the no-timelock TAV swap; slot 3 is the next available re-init slot;
any subsequent verifier swap needs `reinitializer(4)` etc. This is
deliberately a single-shot pattern so a compromised owner cannot
re-migrate at will.

### 3. Update the deploy script

Either patch `contracts/script/RedeployTAVAndMigrate.s.sol` in place or
fork to `RedeployTAVRestoreTimelock.s.sol`. Minimal changes:

- The new TAV uses the patched `CHANGE_DELAY = 2 days` automatically.
- **Skip the verifier+adapter redeploys** (steps 99-106 in the existing
  script). The Path-B verifiers are already correct on-chain — reuse
  the addresses from `kite-testnet.json`:
    - `momentumVerifierAdapter`
    - `meanReversionVerifierAdapter`
    - `yieldRotationVerifierAdapter`
- The new `StrategyVault` impl (deployed via `new StrategyVault(...)`)
  inherits the `reinitializer(3)` bump from step 2.
- `migrateVerifier(a.newTAV)` is still the call per-proxy.

### 4. Broadcast

```bash
# Confirm verifier addresses match deployments JSON
forge script contracts/script/RedeployTAVRestoreTimelock.s.sol \
  --rpc-url $KITE_RPC_URL \
  --private-key $DEPLOYER_PK \
  --broadcast \
  -vvv
```

Expected effects, in one broadcast:

1. Fresh `TradeAttestationVerifier` deployed with `CHANGE_DELAY = 2 days`.
2. Three classes registered (momentum, mean-reversion, yield-rotation)
   via `registerVerifier` against the pre-existing Path-B adapters.
3. Fresh `StrategyVault` impl deployed (same constructor args as the
   current impl — `priceAnchor`, `yieldAnchor`).
4. Each of the 9 phase-6 vaults UUPS-upgraded to the new impl and
   `migrateVerifier(newTAV)` called via `upgradeToAndCall`. Burns
   `reinitializer` slot 3.
5. `kite-testnet.json` patched in-place.

## Verification

```bash
# 1. New TAV uses the 2-day delay
cast call $NEW_TAV 'CHANGE_DELAY()(uint256)' --rpc-url $KITE_RPC_URL
# Expect: 172800

# 2. Each vault points at the new TAV
for v in $(jq -r '.addresses | with_entries(select(.key | startswith("phase6Vault"))) | .[]' \
              contracts/deployments/kite-testnet.json); do
  cast call $v 'tradeAttestationVerifier()(address)' --rpc-url $KITE_RPC_URL
done
# Expect: all return the new TAV address.

# 3. Three classes registered on the new TAV
for cls in $CLASS_MOM $CLASS_MR $CLASS_YR; do
  cast call $NEW_TAV 'verifierOf(bytes32)(address)' $cls --rpc-url $KITE_RPC_URL
done
# Expect: each returns the matching pre-existing adapter address.

# 4. Smoke-test: a new mr signal should still produce TradeAttested
ssh -i ~/.ssh/helios_vps helios@38.49.216.27 \
  'curl -s http://localhost:8006/v1/stats | jq .execs_submitted'
# Expect: non-zero (strategy services don't need to be restarted —
# the vault's stored TAV pointer is the only mutable state involved).
```

## Risk profile during the demo period

While `CHANGE_DELAY = 0`:
- An owner-key compromise can swap in a malicious verifier and start
  attesting fake trades instantly. Mitigation: deployer key is held
  by one operator on a single VPS for the demo window; standard
  hot-wallet hygiene applies.
- Mainnet promotion **must not** happen with `CHANGE_DELAY = 0`. The
  stretch-goal mainnet path either picks up the restored source (this
  doc) or deploys from a different branch where the constant was never
  edited.

## When to run this

Run after:
1. Demo video recorded and submitted.
2. Judges have stopped interacting with the deployed contracts.
3. `v0.6.0` tag is pushed and any acceptance criteria that require the
   no-timelock TAV (none, currently) are met.

Run before:
1. Any external operator is invited to register a strategy or
   allocator.
2. A mainnet promotion broadcast.
