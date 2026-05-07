# Phase 3 Review HIGHs — Deploy Plan

Tracks the on-chain follow-up required after merging the HIGH-severity remediation PRs from `docs/phase-3-review.md`. Code lands in PRs #58, #59 (merged), #60, #61, #62, #63. This doc covers what has to ship to Kite testnet to make those changes effective.

Three deploy units, ordered by risk. **Execute Unit 3 first** (circuits — biggest blast radius, want it baked before layering vault changes on top), then Units 1 + 2 together in one StrategyVault upgrade window.

---

## Unit 1 — Vault upgrades (PRs #60, #62)

**What changes**
- `UserVault` — `setMeta` tightening guard + `IAllocatorVaultForUser.userTotalDeployed` view consumed (PR #60, HIGH #5)
- `AllocatorVault` — `userTotalDeployed` view exposed; capped unwind in `_unwindAndCredit` (PRs #60 + #62, HIGH #8)
- All three vaults — OZ `PausableUpgradeable` mixin (PR #62, HIGH #10)
- `StrategyVault` — `reportNAV` operator/oracle gate + 600s replay window (PR #60, HIGH #7); NAV-share cap on `withdrawToAllocator` (PR #62, HIGH #8)

**Why this is a UUPS upgrade, not a redeploy**
All three vaults are UUPS. `PausableUpgradeable` uses ERC-7201 namespaced storage (slot derived from `keccak256("openzeppelin.storage.Pausable")`), so adding the mixin does not shift any existing slot. New helpers/views add code only.

**Steps**
1. `forge inspect UserVault storage-layout` (and AllocatorVault, StrategyVault) against the deployed bytecode — diff must be empty or appended-only. Block if not.
2. `forge script script/UpgradeVaults.s.sol --rpc-url $KITE_RPC_URL --broadcast` — deploys new impls and calls `upgradeToAndCall(newImpl, "")` on each proxy from the deploy EOA (current owner per `contracts/deployments/kite-testnet.json`).
3. Smoke checks (cast calls from owner):
   - `pause()` → revert on a paused-path entrypoint (`UserVault.deposit`, `AllocatorVault.allocateToStrategy`, `StrategyVault.executeWithProof`)
   - `unpause()` → succeeds
   - `AllocatorVault.userTotalDeployed(user)` returns non-zero for a user with active allocations
   - `StrategyVault.withdrawToAllocator(amount > navOf(allocator))` reverts `WithdrawExceedsNAVShare`
4. Update `contracts/deployments/kite-testnet.json` with new impl addresses (proxies unchanged).
5. `pnpm --filter contracts-abi build` and bump downstream consumers if any errors fired (Pausable adds events).
6. Subgraph: optional `Paused`/`Unpaused` handlers in `subgraph/src/`. Defer unless a UI surface needs them.

**Rollback**
Re-deploy previous impl from the most recent merged-main commit and `upgradeToAndCall` back. No state migration either direction (no init args).

---

## Unit 2 — Oracle anchor redeploy (PR #61)

**What changes**
- `OraclePriceAnchor` / `OracleYieldAnchor` — added `_committedAt` mapping, `unrevokeRoot()` (owner-only), `freshness(root)` view returning 0 when never-committed OR revoked (HIGH #6, HIGH #9)
- `IOracleAnchor` — new `RootUnrevoked` event, `RootNotRevoked` error, `unrevokeRoot()` + `freshness()` interface methods
- `StrategyVault` — replaced `isKnownRoot` with a freshness check using `_MAX_ORACLE_STALENESS_SEC = 180`

**Why this is a fresh deploy, not an upgrade**
Anchors are immutable (per CLAUDE.md "Conventions"). Storage layout changed → must redeploy. StrategyVault is UUPS and bundled into Unit 1's upgrade window.

**Steps**
1. `forge script script/DeployOracle.s.sol --rpc-url $KITE_RPC_URL --broadcast` — deploys fresh `OraclePriceAnchor` + `OracleYieldAnchor`, signer pulled from `ORACLE_SIGNER_PK`.
2. Backfill: have `services/oracle` re-publish the last ~10 minutes of price + yield snapshots to the new anchors so freshness windows aren't empty when StrategyVault repoints.
3. **⚠ Code-change prerequisite (NOT yet landed):** the deployed `StrategyVault` stores `priceAnchor`/`yieldAnchor` as `address public` slots populated at `initialize`. There is currently no admin path to repoint these post-init, so the new impl alone can't pick up the new anchor addresses. Before this unit can ship, add **one** of:
   - (a) Constructor immutables on the new impl (cleanest — `priceAnchor`/`yieldAnchor` become `immutable`, storage slots stay but go unused). Requires PR + tests asserting the impl reads from immutables, not storage.
   - (b) `function setOracleAnchors(address, address) external onlyOwner` on the new impl. Requires PR + tests; one-shot use after upgrade.
   Option (a) preferred — no permanent admin surface, and the impl is one-and-done after upgrade.
4. After the prereq lands: `forge script script/DeployOracle.s.sol …` redeploys the anchors, `script/UpgradeStrategyVault.s.sol` (new) deploys the new impl with new anchor addresses baked in (option a) or upgrades + calls the setter (option b).
4. Old anchors stay live but unreferenced. No migration; old roots become unreachable for execute paths but remain queryable for archival.
5. Update `contracts/deployments/kite-testnet.json` (`oraclePriceAnchor`, `oracleYieldAnchor`).
6. `pnpm --filter contracts-abi build`; rev `services/oracle` config to publish to the new addresses going forward.

**Rollback**
Revert the StrategyVault impl in Unit 1's rollback path; old anchors remain functional, no data loss.

---

## Unit 3 — Circuit + verifier rotation (PR #63) ⚠ EXECUTE FIRST

**What changes**
- `momentum_v1.circom` — added `was_long` private input + branched signal-flip logic (HIGH #11), self-swap forbidden via `IsEqual` (HIGH #12), `Num2Bits(128)` range checks on `amount_in` / `min_amount_out` / `max_position_size` (HIGH #13)
- `mean_reversion_v1.circom` — self-swap forbidden + `Num2Bits(128)` range checks (HIGH #12, #13)
- `yield_rotation_v1.circom` — untouched

**Blast radius**
Touches: zkey → vkey → Verifier.sol → adapter → `TradeAttestationVerifier.verifiersByClass` → prover service witness inputs → strategy SDK. Old proofs stop validating against TAV the instant `setVerifier` lands, so prover + TAV rotation must be coordinated.

**Steps**
1. `cd circuits && make momentum_v1 mean_reversion_v1` — regenerates R1CS, zkey, vkey, `MomentumV1Verifier.sol`, `MeanReversionV1Verifier.sol`. PTAU 16 still fits (constraint counts under 50% budget after the additions).
2. Commit the regenerated `Verifier.sol` + vkeys to the repo. (PR #63 deliberately did not include these to keep the diff non-breaking; they are required here.)
3. `forge script script/DeployVerifier.s.sol --sig "run(string)" momentum_v1 --rpc-url $KITE_RPC_URL --broadcast` — deploys new raw verifier + adapter. Repeat for `mean_reversion_v1`.
4. **Coordinated cutover (single tx batch or back-to-back txs):**
   - Roll `services/prover` to the new wasm + zkey artifacts (PM2 restart on the VPS — see `reference_vps.md`).
   - `cast send $TAV "setVerifier(bytes32,address)" $MOMENTUM_CLASS_ID $NEW_MOMENTUM_ADAPTER`
   - `cast send $TAV "setVerifier(bytes32,address)" $MEAN_REVERSION_CLASS_ID $NEW_MR_ADAPTER`
   - Yield-rotation untouched.
5. **Strategy SDK** — `packages/strategy-sdk/helios/classes/momentum.py` must populate `was_long` from the agent's tracked side. The runtime already knows current position; plumb it into the witness builder.
6. **Reference strategies** — `reference-strategies/momentum_v1/` rebuild + redeploy if the SDK signature changed.
7. Run `scripts/e2e-scenario.sh` end-to-end against the fresh stack. Block on green.
8. Update `CLAUDE.md` "Key addresses" block + `contracts/deployments/kite-testnet.json` with new raw-verifier and adapter addresses for both classes. Note the rotation date in the same line as the existing `2026-05-05` rotation marker.

**Rollback**
`tav.setVerifier(classId, oldAdapter)` reverts the class map. Old adapters never get unregistered, so this is one tx per class. Prover stays on new artifacts (they accept the old class layout's public inputs as a strict subset — verify before assuming).

---

## Sequencing summary

| Order | Unit | Window | Verify with |
|---|---|---|---|
| 1 | Unit 3 — circuits | ~30–45 min | `scripts/e2e-scenario.sh` |
| 2 | Units 1 + 2 — vaults + oracles | ~30–45 min | smoke checks above + e2e replay |

Total: two upgrade windows on Kite testnet. Owner key is the deploy EOA recorded in `kite-testnet.json`. Run from the same machine that has Foundry + the deploy keystore unlocked.

## Pre-flight checklist (per window)

- [ ] `forge test -vv` clean on the head commit
- [ ] `forge inspect storage-layout` diff reviewed for every UUPS proxy in scope
- [ ] `kite-testnet.json` snapshotted (committed) so rollback addresses are recoverable
- [ ] VPS prover service health-checked (`pm2 logs prover`) before circuit cutover
- [ ] Subgraph indexing lag < 1 minute (`graph-node` block height vs RPC tip)
- [ ] e2e scenario passes against current testnet before any change

## Owner / contact

- Deploy EOA: see `contracts/deployments/kite-testnet.json`
- Oracle signer: `ORACLE_SIGNER_PK` env on the VPS
- Reputation signer: `REPUTATION_SIGNER_PK` env on the VPS
- Prover host: VPS Servarica Montreal `helios@38.49.216.27` (`reference_vps.md`)
