# Kite Passport & AA SDK integration notes

This doc captures what we know about Kite's AA SDK + Passport from scanning their
docs (`docs.gokite.ai/kite-chain/account-abstraction-sdk`,
`docs.gokite.ai/kite-agent-passport/kite-agent-passport`) and exercising the
toolchain against the testnet. Future Claude sessions start here before touching
Passport wiring.

## Versions

- **SDK**: `@gokite/aa-sdk` — exact version pinned once Phase 0 smoke test runs.
- **Chain**: Kite testnet, chain id `2368`, RPC `https://rpc-testnet.gokite.ai`.

## What Helios uses Passport for

1. **User root key** — signs the meta-strategy once. `UserVault.setMetaStrategy`
   validates the signature against this key.
2. **Allocator session** — derived session from the user's Passport when they
   `delegateToAllocator`. TTL-bounded, revocable.
3. **Strategy session** — derived from the allocator's session when it calls
   `AllocatorVault.allocateToStrategy`. The strategy's operator also gets its
   own session for `executeWithProof` submissions.

Each layer is BIP-32 hierarchical — compromising a strategy session affects
only that strategy's allocation; compromising the allocator session stays
bounded by the user's meta-strategy constraints (enforced on-chain).

## Status (2026-04-25): BLOCKED on public Passport access

Kite team announcement: Passport public launch pending; hackathon deadline
extended by at least 2 weeks. We cannot run the smoke test or wire any
Passport-signed flow against live testnet until access lands. **This block is
external, not a user-action item.**

In the meantime, Phase 1 builds with EOA signatures as Passport stubs at every
touchpoint, then swaps to real Passport calls when access is available. See
"Passport swap-in checklist" below.

## Passport swap-in checklist (run when access lands)

When Kite enables Passport publicly:

1. Pin the exact `@gokite/aa-sdk` version in this doc; install in `frontend/`
   and `scripts/kite-passport-smoke.mjs`.
2. Run `scripts/kite-passport-smoke.mjs` end-to-end; record tx hash, gas, and
   SDK version in the "Run log" section below.
3. Replace EOA-signature stub at `UserVault.setMetaStrategy` integration —
   change client signing from `wallet.signTypedData` to Passport-derived
   signature; on-chain side already supports EIP-1271 (verify this in §3 of the
   open questions list).
4. Replace allocator session-key stub with Passport BIP-32 child derivation.
5. Replace strategy operator submission EOA with paymaster-sponsored
   gasless userOp per `docs.gokite.ai/kite-chain/9-gasless-integration`.
6. Re-run `scripts/e2e-scenario.sh` and confirm the Phase 1 vertical slice
   still passes end-to-end.
7. Tick the Passport item in `TODO.md` Phase 0 outstanding section.

## Phase 0 smoke test (deferred)

**Goal.** Confirm the SDK can mint a Passport, derive a session, and send a
userOp to Kite testnet.

Location: `scripts/kite-passport-smoke.mjs` (scaffold present; concrete SDK
calls fill in once access lands).

Shape:

```
1. Load KITE_PASSPORT_SIGNER_PK from .env
2. Initialize AA SDK client against KITE_RPC_URL
3. Mint a Passport (or load an existing one)
4. Derive a session with a small TTL (e.g. 5 min) and a minimal allow-list
5. Send a nop userOp — call `Helios.heartbeat()` deployed in Phase 0
6. Assert the tx is confirmed, record the hash
7. Revoke the session and assert the next call fails
```

Record: SDK version, gas cost, latency, any unexpected friction in
`docs/kite-passport-notes.md` (this file) so we know what we're importing
into production.

## Gasless flow (Phase 1+)

Per `docs.gokite.ai/kite-chain/9-gasless-integration`, agent userOps can be
sponsored. Helios uses this for the strategy operator's `executeWithProof`
submissions — the strategy agent shouldn't need to hold KITE for gas. The
paymaster config goes in each Strategy Service's env.

## Known open questions

- Does the AA SDK expose hierarchical session derivation natively, or do we
  derive the child sessions ourselves from the parent's BIP-32 path?
- What's the max session TTL? Phase 1 meta-strategies default to 30 days.
- Does Kite support EIP-1271 on Passport contracts? We need this for the
  meta-strategy signature check in `UserVault.setMetaStrategy`.

Answer each of these in Phase 0 smoke-testing and update this doc.
