# ReputationAnchor V1 → V2 cutover

> **STATUS: DONE (2026-05-11 — WS11)**. V2-bis anchor + fresh registries
> (SR-v3 `0xe6c2cfCa…`, AR-v2 `0xb673e6F8…`) are live on Kite testnet
> bound to V2-bis (`0x2b6c5f36…`) at construction. The 9 Phase-6 vaults
> were upgraded to setter-enabled impls and rebound to SR-v3. Cross-chain
> single-update path proven end-to-end (Base→Kite GUID `0x24fd5344…`
> moved SR-v3 `currentReputation` 0 → 750 in a single hop). Engine +
> frontend + VPS env are all pointed at V2-bis + SR-v3 + AR-v2 +
> Goldsky `helios/v0.7.0`.
> The narrative below is preserved as the *why* and as a runbook for
> any future re-cutover.

Phase 2 ships `ReputationAnchorV2` (typehash version 2 + `componentsHash`)
alongside the immutable `ReputationAnchorV1` deployed in Phase 1. The
two anchors cannot share a registry binding.

This doc fixes the *failure mode* visibility called out in the Phase-2
review follow-up (`docs/phase2-review-followup.md` §15): without it a
reader assumes V2 is "wired and ready" because `setRegistries(V2)`
exists, but the first `postReputationUpdate` on V2 reverts.

## Why V2 cannot drive V1-deployed registries

`StrategyRegistry` and `AllocatorRegistry` gate state-changing reputation
updates on the anchor address baked into the registry at construction
time:

```
// contracts/src/StrategyRegistry.sol:19
address public immutable reputationAnchor;
…
function updateReputation(address strategyId, int256 delta) external {
    if (msg.sender != reputationAnchor) revert NotReputationAnchor();
    …
}
```

The registry's `reputationAnchor` is **immutable**. Phase-1 registries
were constructed with the V1 anchor address, so any future caller that
isn't V1 reverts with `NotReputationAnchor` — including V2.

`ReputationAnchorV2.setRegistries(strategyRegistry, allocatorRegistry)`
exists and the V2 contract will store + emit a `ComponentsAnchored`
event regardless of how `setRegistries` was wired. But the side-effect
of V2 — pushing `delta` to the registry's `currentReputation` — only
fires when the registry trusts V2 as its anchor, which Phase-1
registries do not.

## What V2 actually does today

Until the registries are redeployed pointing at V2, V2 is best modelled
as a **sidecar publisher**: it stores `ReputationData` per actor and
emits `ReputationPosted` + `ComponentsAnchored` so the audit page and
subgraph can render the v2 score breakdown. The registries continue to
hold a V1-only `currentReputation` value (last touched by V1 before
Phase-2 deploy or, more commonly, never touched if V1 was deactivated
mid-Phase-1).

The reputation engine (`services/reputation/`) is configured to post to
V2 in Phase 2; the registries staying on V1 is intentional and called
out in the `project_reputation_phase1_simplified` memory + TODO note.

## Cutover paths (Phase 5 work)

Three options, in order of cleanest to most pragmatic:

1. **Redeploy registries pointing at V2.** Construct
   `StrategyRegistryV2` + `AllocatorRegistryV2` with
   `reputationAnchor = ReputationAnchorV2` and migrate state via the
   existing UUPS upgrade hooks. Registries are themselves non-upgradeable
   (only the vaults are), so migration means re-registering every
   strategy/allocator in the new registries. Tracked under Phase 5 in
   TODO.md alongside the staking-token redeploy.

2. **Add a `secondaryReputationAnchor` slot.** Modify both registries to
   accept updates from one of two anchor addresses, then activate V2
   without redeploy. Requires a new registry release and breaks the
   "registry is immutable" invariant Phase 1 sold. Not recommended.

3. **Accept V2 as a sidecar permanently.** Treat the registry's
   `currentReputation` as deprecated and read everything from the
   subgraph (which already prefers V2 entries via `source = "V2"`).
   This is the de-facto Phase-2 state and the smallest change.

Phase 5 executes path (1) on testnet (the registry redeploy happens
regardless of mainnet timing — it's needed to bind V2 to the live
contracts so allocator capital flow tracks v2 scores). Mainnet
promotion is a stretch (see `docs/deployment-strategy.md`); if
exercised it re-runs the same redeploy on chain 2366. Until path (1)
ships the codebase is in path (3): V2 publishes, V1 registries hold
the legacy scalar, and the subgraph + audit page surface both.

## What NOT to do

- **Do not call `ReputationAnchorV2.setRegistries(V1Registry, V1Registry)`**.
  V2's `setRegistries` is `onlyOwner` and one-shot
  (`RegistriesAlreadySet`), so a mistaken call cannot be reverted —
  every subsequent `postReputationUpdate` for a STRATEGY or ALLOCATOR
  actor would revert with `NotReputationAnchor` from the registry, and
  the engine's tick would stall. The Phase-2 deploy script
  (`script/DeployPhase2.s.sol`) intentionally **does not** call
  `setRegistries` on V2 — verify before running any post-deploy
  parameter wiring.

- **Do not retire V1 before Phase 5.** V1 is still the registry's
  authority for `currentReputation`. Removing V1's signer rotation
  capability or deactivating its OApp connection breaks any path that
  reads `Strategy.currentReputation` from chain state instead of the
  subgraph.

## Operator checklist before flipping V2 into a primary role

When Phase 5 is ready to migrate:

1. Deploy fresh `StrategyRegistryV2` + `AllocatorRegistryV2` with
   `reputationAnchor = ReputationAnchorV2`.
2. Re-register every active strategy + allocator into the new registries
   (state migration script lands with the redeploy).
3. Update `AllocatorVault.setStrategyRegistry` / `.setAllocatorRegistry`
   to point at the V2 registries. Both setters exist
   (`AllocatorVault.sol`) and emit events, so the swap is observable.
4. Call `ReputationAnchorV2.setRegistries(V2Registry, V2Registry)` —
   one-shot, no rollback.
5. Decommission V1 anchor only after a full reputation tick succeeds
   against V2-connected registries.

Until step (1) lands, V2 stays sidecar.
