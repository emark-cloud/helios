# Phase 5 review — critical / high findings

Review date: 2026-05-08. Range reviewed: `aeb53b9^..HEAD` (PRs #82, #88, #89).
Scope: cross-chain Solidity contracts, oracle service + strategy SDK runtime,
subgraph cross-chain entities, frontend cross-chain watcher.

Three review surfaces were swept. The contract surface has serious bugs that
must land in a follow-up patch before any execution-chain deployment is wired
to the canonical Kite anchor. Services + SDK and subgraph + frontend came back
clean against the critical/high bar.

---

## CRITICAL

### C1 — `HeliosOApp.sendReputationUpdate` is unauthenticated; reputation is forgeable cross-chain

**File:** `contracts/src/HeliosOApp.sol:83-112`

`sendReputationUpdate(dstEid, actor, actorType, data, options)` has no caller
gate. Any contract on Base / Arb can call it with arbitrary `actor` + `data`.
The packet flows through the trusted LZ peer; on Kite `_lzReceive` →
`_applyReputation` → `reputationAnchor.postCrossChainUpdate(actor, actorType,
data)`. `ReputationAnchor.postCrossChainUpdate` only authorizes `msg.sender ==
oApp` (line 128) — it trusts whatever the OApp passes through.

`ReputationAnchor._applyUpdate` writes `_reputations[actor] = data` wholesale
and deltas the score into `StrategyRegistry` / `AllocatorRegistry`. So an
attacker on Base/Arb zeros a competitor strategy or maxes themselves out,
breaking the reputation-driven allocation premise of v1.

**Fix:** Restrict `sendReputationUpdate` to allowlisted callers (e.g.
`isStrategyVault[msg.sender]`, mirroring the `queueAttestation` gate at line
119) and require `actor == msg.sender` (or `actor` belongs to the caller).

### C2 — `HeliosOApp.bridgeAndDeploy` is also unauthenticated

**File:** `contracts/src/HeliosOApp.sol:173-199`

Same shape as C1. Anyone calls `bridgeAndDeploy(dstEid, strategyOnDst,
amount)`. On the destination, `_handleBridgeDeploy` invokes
`IBridgeReceiver(bridgeReceiver).onBridgeAndDeploy(strategy, amount)` with
attacker-chosen amount. `bridgeReceiver` is `address(0)` today (the call is a
no-op), but the contract advertises this hook as the capital path; once
`setBridgeReceiver` lands, every credit is forgeable.

**Fix:** Same allowlist gate as C1; bind to a verifiable burn proof on the
source chain rather than the OFT.send "by convention" pairing the doc-comment
describes.

---

## HIGH

### H3 — `StrategyVault._forwardAttestationIfRemote` clobbers Kite-side reputation to zero on every remote trade

**File:** `contracts/src/StrategyVault.sol:638-672` (Phase 5 diff)

The hook always queues `currentScore: 0, totalAttestedTrades: 1,
totalRealizedPnL: 0, maxDrawdownBps: 0, proofValidityRateBps: 10_000`. When
the keeper flushes via `flushAttestationsFor` → `_handleReputationBatch` →
`postCrossChainUpdate` → `_applyUpdate`, `ReputationAnchor` copies the struct
wholesale. The first successful Phase-5 trade on Base / Arb therefore resets
that strategy's authoritative Kite-side score to 0 and propagates a negative
delta to `StrategyRegistry.updateReputation`. Triggers automatically — no
adversary required.

**Fix:** Either route remote attestations to a separate counter-only anchor
entrypoint (e.g. `postCrossChainTradeTick`) that increments
`totalAttestedTrades` without overwriting `currentScore` / `totalRealizedPnL`,
or have the canonical-side OApp re-fetch `prev` on Kite and merge before
calling the anchor.

### H4 — Cross-chain `lastUpdateBlock` permanently DoSes future Kite reputation updates

**File:** `contracts/src/StrategyVault.sol:660` + `contracts/src/ReputationAnchor.sol:175`

`_forwardAttestationIfRemote` writes `lastUpdateBlock: block.number` — the
*remote* chain's block number (Arb sequencer numbers >190M; Kite testnet is in
the low tens of thousands). `_applyUpdate` enforces `data.lastUpdateBlock >
prev.lastUpdateBlock` or reverts `StaleUpdate()`. After one cross-chain
message lands on Kite, every subsequent off-chain `postReputationUpdate` from
the Kite reputation engine reverts until Kite catches up to the foreign block
number — effectively forever. Combined with C1, this becomes a permanent
denial-of-reputation-updates for any targeted actor.

**Fix:** Have the canonical-side OApp re-stamp `data.lastUpdateBlock =
block.number` (Kite's) before forwarding, or switch the freshness check to
`block.timestamp`.

### H5 — `_lzReceive` single/batch discriminator collides at `seq == 64`

**File:** `contracts/src/HeliosOApp.sol:218-227`

The receiver branches on `second == 0x40` to pick batch vs. single decode.
For a single update, the second 32-byte word is `seq` (uint64). For a batch,
it's `0x40` (offset to dynamic array). When a legitimate single update reaches
`seq == 64`, the heuristic routes it into the batch decoder, which
`abi.decode`s as `(PayloadKind, ReputationBatchEntry[])` and reverts on shape
mismatch. LZ V2 retries forever, bricking the path until the packet is
force-cleared.

**Fix:** Give single and batch distinct `PayloadKind` enum values (e.g.
`ReputationUpdateV1 = 1`, `ReputationBatchV1 = 3`); route on the kind byte
alone, no calldata heuristic.

### H6 — `maxPendingPerStrategy` has no upper bound; owner misconfig can brick a flush packet

**File:** `contracts/src/HeliosOApp.sol:76-79, 138-169`

`setMaxPendingPerStrategy(cap)` only enforces `cap > 0`. Receiver-side
`_handleReputationBatch` loops with an external call per entry; an over-large
cap pushes `_lzReceive` past the executor gas budget and bricks the packet.

**Fix:** Cap at a small constant (e.g. 64) or chunk flushes into fixed-size
sub-batches in `flushAttestationsFor`.

---

## Composite attack

C1 + H3 + H4 compose into a one-shot reputation-wipe. From a $0 contract on
Base Sepolia:
1. C1 lets the attacker forge any `actor` + `data` over the LZ peer.
2. H4 lets them set `lastUpdateBlock = type(uint256).max`, freezing the engine
   from ever recovering that actor.
3. H3 (the legitimate remote-attestation path on the target's first real
   trade) finishes the job by zeroing the score even if H4 wasn't exercised.

Patching C1 alone resolves the adversarial path; H3 + H4 must still be patched
because they trigger on legitimate use.

---

## Clean surfaces

### Services + SDK

- EIP-712 type-hashes / domain names / versions in `services/oracle/src/oracle/anchor.py:55-117`
  match `contracts/src/OraclePriceAnchor.sol:37,53` and
  `contracts/src/OracleYieldAnchor.sol:23,39` byte-for-byte. Cross-domain
  replay (price ↔ yield) blocked by distinct `name`.
- `ORACLE_SIGNER_PK` handling: only error sanitized to `type(exc).__name__`
  with `from None` (`anchor.py:171-174`); never logged, persisted, or shipped.
- `MultiChainAnchorPoster` re-signs per chain with chainId + verifyingContract
  in the EIP-712 domain — cross-chain replay across canonical + mirrors
  blocked.
- `StrategyVault._runSwapTrades` re-validates router calldata
  (`contracts/src/StrategyVault.sol:558-623`): recipient, tokenIn/tokenOut,
  amountIn, amountOutMinimum, target, selector, value all bound to manifest +
  publicInputs. The Phase-5 V3 / Aave calldata builders are bounded by the
  on-chain whitelist.
- Aave V3 path in `yield_rotation_v1/executor.py` is currently dead code —
  `executeYieldRotationWithProof` rejects non-empty `trades[]`. No live attack
  surface.

### Subgraph + frontend

- `subgraph/src/helios-oapp.ts`: all four handlers cover send-before-receive
  and receive-before-send orderings; required fields initialized on every
  entity-creation branch.
- `CrossChainReputationMessage.id` = LZ GUID (globally unique per packet);
  `Strategy.id` = registry address (collapsed across chains, with
  `executingChainIds[]` recording venue chains). No id collisions.
- `frontend/src/lib/crossChainWatcher.ts` filters viem `watchContractEvent` by
  the configured OApp address; resolved details only drive cosmetic
  animations, no `useSendTransaction` consumes them.
- RPC URLs sourced from `NEXT_PUBLIC_*` build-time envs, not query params.

---

## Test-coverage gaps that let the bugs through

- No test asserts `sendReputationUpdate` fails for an unauthorized caller
  (because there is no such gate).
- No integration test runs the StrategyVault hook end-to-end into a real
  `ReputationAnchor` to observe the score-zeroing effect.
- No test exercises a single-update payload with `seq == 64` against the
  batch/single discriminator.
- No test for `bridgeAndDeploy` + `onBridgeAndDeploy` with a non-zero
  `bridgeReceiver`.
- No test pins the EIP-712 type-hash digest against an independent encoder
  (a future refactor swapping `encode_typed_data` could silently drift).

---

## Fix plan

All six findings ship in a single `phase-5-fix` PR with three commits. Six
findings, three files of touch (`HeliosOApp.sol`, `CrossChainCodec.sol`,
`StrategyVault.sol`) plus one new entrypoint on `ReputationAnchor.sol`. The
codec change couples to the OApp receive path and the test additions share a
harness, so splitting into separate PRs would only slow review.

Phase-5 cross-chain wiring is not yet broadcast (manifests carry `0xdEaD`
placeholder addresses), so the wire-format change in commit 2 lands before any
peer goes live. After peers are live this becomes a coordinated upgrade.

### Commit 1 — gate cross-chain entrypoints (C1, C2)

**File:** `contracts/src/HeliosOApp.sol`

- `sendReputationUpdate`: require `isStrategyVault[msg.sender]` and
  `actor == msg.sender`. Mirrors the `queueAttestation` gate (line 119).
- `bridgeAndDeploy`: require `isStrategyVault[msg.sender]` and
  `strategyOnDst == msg.sender` (a vault sending capital to its remote
  sibling).

A vault can only attest its own reputation and only bridge to itself. The
contract surface stops accepting forged actors entirely.

**Tests in `HeliosOApp.t.sol`:**
- `test_sendReputationUpdate_revertsForUnauthorizedCaller`
- `test_sendReputationUpdate_revertsWhenActorMismatch`
- `test_bridgeAndDeploy_revertsForUnauthorizedCaller`
- `test_bridgeAndDeploy_revertsWhenStrategyMismatch`

### Commit 2 — codec discriminator + cap (H5, H6)

**Files:** `contracts/src/lib/CrossChainCodec.sol`,
`contracts/src/HeliosOApp.sol`

H5:
- Add `ReputationBatchV1 = 3` to `CrossChainCodec.PayloadKind`.
- `encodeReputationBatch` emits `(PayloadKind.ReputationBatchV1, entries)`;
  `decodeReputationBatch` requires `kind == ReputationBatchV1`.
- `_lzReceive` becomes a clean switch on `kind` — drop the
  `second == 0x40` calldata heuristic entirely.

H6:
- Add `_MAX_PENDING_HARD_CAP = 64` constant in `HeliosOApp`;
  `setMaxPendingPerStrategy` enforces `cap <= _MAX_PENDING_HARD_CAP`.

**Tests:**
- `test_receive_singleUpdateWithSeq64_doesNotMisrouteToBatch` — the H5 canary.
  Sends a single update with `seq == 64`, expects the anchor to be called
  exactly once (not the batch decoder reverting).
- `test_receive_batchUsesBatchKind` — flush a batch, observe the new kind on
  the wire.
- `test_setMaxPendingPerStrategy_revertsAboveHardCap`.

### Commit 3 — counter-only cross-chain attestation (H3, H4)

**Files:** `contracts/src/ReputationAnchor.sol` (new entrypoint),
`contracts/src/interfaces/IReputationAnchor.sol`, `contracts/src/HeliosOApp.sol`,
`contracts/src/StrategyVault.sol`.

Add `postCrossChainTradeTick(address actor)` to `ReputationAnchor`. It is
gated `msg.sender == oApp`, increments `_reputations[actor].totalAttestedTrades
+= 1`, and **does not** touch `currentScore`, `totalRealizedPnL`,
`maxDrawdownBps`, `proofValidityRateBps`, or `lastUpdateBlock`. No registry
delta is propagated (count-only signal). H4 falls out automatically because
`lastUpdateBlock` is no longer written from the cross-chain path.

`HeliosOApp._handleReputationBatch` routes batch entries to
`postCrossChainTradeTick(strategy)` (not `postCrossChainUpdate`). The
single-update path (`sendReputationUpdate`) stays on `postCrossChainUpdate` —
it carries an authoritative engine-signed payload, not a tick.

`StrategyVault._forwardAttestationIfRemote` simplifies: the
`ReputationData` struct field is no longer read on the receiving side, so the
hook can pass a zeroed `data` struct (or we can change `queueAttestation` to
take only `address strategy`). Smaller change is to leave the queue shape
alone for now and document that everything except `strategy` is ignored
post-tick.

V1 is registry-bound today; V2 is sidecar (per `project_reputation_phase1_simplified.md`
memory). Add the entrypoint to **V1** for Phase 5 and carry it into V2 at the
Phase-5 cutover documented in `docs/reputation-v1-v2-cutover.md`.

**Tests in new `ReputationAnchorCrossChain.t.sol` + extending `StrategyVaultCrossChain.t.sol`:**
- `test_forwardAttestation_doesNotZeroScore` — set a Kite-side score to 500,
  flush a remote tick, observe `currentScore == 500` after.
- `test_engineUpdateStillWorksAfterCrossChainTick` — the H4 canary. Flush a
  tick, then post a real `postReputationUpdate` from the engine, expect
  success (not `StaleUpdate`).
- `test_forwardAttestation_incrementsAttestedTradeCount`.
- `test_postCrossChainTradeTick_onlyOApp`.

### Deployment impact

- **`HeliosOApp`**: not yet wired to live peers — fresh deploy on Base / Arb /
  Kite, then `setPeer` on each side.
- **`ReputationAnchor` V1**: registry-bound; needs an upgrade or fresh deploy
  to add `postCrossChainTradeTick`. V1 is non-upgradeable per CLAUDE.md
  ("Registries and anchors are immutable"), so this is a fresh deploy +
  re-wire from the registries.
- **`ReputationAnchor` V2**: not registry-bound; carry the new entrypoint
  forward and ship the cutover that `docs/reputation-v1-v2-cutover.md` plans.
- **`StrategyVault`**: impl-only change (storage layout unchanged — `heliosOApp`
  slot stays); upgrade through the existing UUPS path on Kite. The Phase-5
  Base / Arb StrategyVault implementations can be patched directly before
  first deploy.
- **Subgraph / FE**: no changes. The `AttestationsFlushed` /
  `ReputationMessageReceived` events keep their shapes; only the on-chain
  effect on the anchor changes.

### Out of scope for this PR

- The composite-attack invariant tests (forge-fuzz that no sequence of
  cross-chain messages can ever lower an actor's `currentScore` on Kite) are
  worth adding but belong in a Phase-6 hardening pass.
- An EIP-712 type-hash digest pin (called out as a coverage gap above) is
  also a Phase-6 hardening item.

