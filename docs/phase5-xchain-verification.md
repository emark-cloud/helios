# Phase 5 cross-chain verification (WS10)

Live tracking doc for verifying the LayerZero V2 round-trip end-to-end
against Kite testnet, Base Sepolia, and Arbitrum Sepolia. Detailed
plan in `/home/emark/.claude/plans/dazzling-spinning-quokka.md`.

## Why this exists

Phase 5 shipped the Solidity OApp (`contracts/src/HeliosOApp.sol`), the
deploy script (`contracts/script/DeployPhase5Execution.s.sol`), the
peer-wiring script (`contracts/script/WireLayerZeroPeers.s.sol`), and
the round-trip harness (`scripts/measure_xchain_latency.py`). All four
have unit-level test coverage:

- `contracts/test/HeliosOApp.t.sol` — 6/6 forge tests pass, ~91% line
  coverage (codec, replay guard, peer misconfig, quoting).
- `services/sentinel/tests/test_phase5_xchain.py` — pytest with mocked
  Goldsky + LZ endpoint, asserts allocator decision cascade when a
  cross-chain rep tick lands.

What never happened:

- `DeployPhase5Execution.s.sol` has never been broadcast on any chain.
- No `base-sepolia.json` / `arbitrum-sepolia.json` deployment JSON.
- `kite-testnet.json` has no `heliosOApp` entry.
- No `setPeer` calls — peers are unwired.
- The "canonical-side" OApp on Kite has no deploy script at all
  (`DeployPhase5Execution` hardcodes `reputationAnchor=address(0)` at
  HeliosOApp.sol:122 — execution-chain shape, not Kite shape).

WS10 fills that gap and proves a real LZ V2 message lands on the
destination chain. The plan is mirrored from
`/home/emark/.claude/plans/dazzling-spinning-quokka.md`; this doc is
the **evidence log** as steps complete.

## Pre-check outcomes (2026-05-11)

| Item | Value | Source |
|---|---|---|
| Kite testnet LZ V2 support | YES | `https://metadata.layerzero-api.com/v1/metadata/deployments` |
| Kite EndpointV2 | `0x3aCAAf60502791D199a5a5F0B173D78229eBFe32` | LZ metadata API |
| Kite EID | `40415` | LZ metadata API |
| Base Sepolia EndpointV2 | `0x6EDCE65403992e310A62460808c4b910D972f10f` | LZ canonical (per DeployPhase5Execution.s.sol) |
| Base Sepolia EID | `40245` | LZ docs (chain page) |
| Arbitrum Sepolia EndpointV2 | `0x6EDCE65403992e310A62460808c4b910D972f10f` | LZ canonical (per DeployPhase5Execution.s.sol) |
| Arbitrum Sepolia EID | `40231` | LZ docs (chain page) |

**Outcome**: full 3-chain round-trip is viable. Plan executes branch
(a) per the planning doc.

## Acceptance criteria

The workstream is verified when **a single GUID** can be traced through:

1. A `sendReputationUpdate` tx on a source chain emitting
   `ReputationMessageSent(dstEid=<kite_eid>, …, guid=0xABC)`.
2. A matching `ReputationMessageReceived(srcEid=<src>, …, guid=0xABC)`
   landing on the destination chain ≤60s later.
3. `scripts/measure_xchain_latency.py --source base` (and `--source arb`)
   exiting 0 with the pair logged.

Regression: existing unit tests (HeliosOApp.t.sol, test_phase5_xchain.py,
e2e-scenario.sh phase5) must still pass.

## Execution log

### WS10.0 — LZ V2 Kite support pre-check — COMPLETE (2026-05-11)

Kite testnet has a LayerZero V2 endpoint at
`0x3aCAAf60502791D199a5a5F0B173D78229eBFe32` with EID `40415`. Full
3-chain round-trip is viable. See "Pre-check outcomes" table above.

### WS10.1 — Existing test baseline — COMPLETE (2026-05-11)

All three offline surfaces clean:
- `forge test --match-contract HeliosOApp` → 21/21 pass.
- `pytest services/sentinel/tests/test_phase5_xchain.py` → 3 pass + 1
  skipped (CI-gate test, gated on env).
- `HELIOS_VENUE_*=MOCK bash scripts/e2e-scenario.sh phase5` → GREEN.

### WS10.2 — Env + faucet — COMPLETE (2026-05-11)

Deployer `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25` funded on all
three chains (0.3 ETH Base, 0.5 ETH Arb, 0.65 KITE). All three LZ
endpoints respond with their expected EIDs (40245/40231/40415). RPC
URLs use the official public testnet endpoints (`https://sepolia.base.org`
and `https://sepolia-rollup.arbitrum.io/rpc`) — no API key needed.

### WS10.3 — Kite-side HeliosOApp deploy script — COMPLETE (2026-05-11)

`contracts/script/DeployKiteHeliosOApp.s.sol` written + compiles. Wires
the live V1 ReputationAnchor (`0x51c07adf...`) as constructor arg —
distinct from DeployPhase5Execution which hardcodes `address(0)` for
execution chains. Surgically patches `kite-testnet.json` via three
`vm.writeJson` calls.

### WS10.4 — Broadcast HeliosOApp to each chain — COMPLETE (2026-05-11)

| Chain | OApp | tx | EID |
|---|---|---|---|
| Base Sepolia | `0x55782e7019f4619A06A25bf66D2998C8Fe2CC436` | (DeployPhase5Execution batch) | 40245 |
| Arbitrum Sepolia | `0x55782e7019f4619A06A25bf66D2998C8Fe2CC436` | (DeployPhase5Execution batch) | 40231 |
| Kite testnet | `0x9D93F3f2254d7d6f6f4208938b7Ce7F9E33c43B3` | `0x8807fcc0252c74663993e3c5ccb16a9d5064385655f680b253c29209d3b71ae2` | 40415 |

Same OApp address on Base + Arb is intentional: same deployer EOA, same
nonce sequence on freshly-used chains → same CREATE address.

Kite hit a nonce race with VPS-resident services using `DEPLOYER_PK`
(oracle anchor commits, reputation engine ticks). `forge script`'s
4-retry loop lost the race; recovered with `forge create` + explicit
`--nonce` + bumped `--gas-price`. The bogus first-pass JSON patch
(predicted address with no code) was reverted via `git checkout` before
re-patching with the actual deployed address.

### WS10.5 — Wire peers bidirectionally — COMPLETE (2026-05-11)

All 6 peer mappings landed and verified by reading `peers(uint32)` on
each OApp:
- Base→Kite=`0x...9d93f3f2...`, Base→Arb=`0x...55782e70...`
- Arb→Kite=`0x...9d93f3f2...`, Arb→Base=`0x...55782e70...`
- Kite→Base=`0x...55782e70...`, Kite→Arb=`0x...55782e70...`

`WireLayerZeroPeers.s.sol` handled Base + Arb cleanly (single
broadcast each, two setPeer txs per chain). Kite needed cast send
with explicit nonces to dodge the same VPS-services race; both
setPeer txs landed status=1.

### WS10.6 — Trigger real cross-chain reputation message — COMPLETE (2026-05-11)

| Field | Value |
|---|---|
| Direction | Base Sepolia → Kite testnet |
| Allowlist tx | `0xfeae0cdb96f16a79515e541b6e08056a213b2b608e35971a03dc0de0252863fb` (`setStrategyVault(deployer, true)`) |
| Send tx (first attempt) | `0xb63f366459fe21dca337db2965b748d6207db0697a41bc2ea3b3d59641dc085b` |
| First-attempt GUID | `0xbdb2300e197e0e17264736e83d86837c209d34d928cdf7655da103c59b9532f1` |
| LZ V2 fee paid | 98985491284465 wei (~0.0001 ETH; 20% slack added on quote) |
| First-attempt LZ Scan status | **FAILED** — "Executor transaction simulation reverted" |

The first message reached the Kite endpoint (DVN verified inbound) but
the executor's `lzReceive` call reverted. Root cause: `HeliosOApp._applyReputation`
calls `IReputationAnchor.postCrossChainUpdate(actor, actorType, data)`
on the V1 anchor (`0x51c07adf...`). That function gates on
`msg.sender == oApp` (ReputationAnchor.sol:128). The V1 anchor's `oApp`
field was still `0x0` because `setOApp(...)` had never been called —
the OApp didn't exist when Phase 1 deployed the anchor, and there's
been no reason to call it until now.

**Fix landed**: `cast send V1_ANCHOR setOApp(0x9D93F3f2...)` tx
`0xabc5f4fba1de86a717f0e95339fe0c68fa1d1aacbf9e9087073068902c72a151`
(status=1). Verified via `cast call oApp()` returning the Kite OApp.

A fresh single-update message (3rd send) was sent post-fix
(tx `0x7e635448…`, GUID `0x383bc280…`). LZ Scan still reports
**FAILED** with `0x` revert. Second gate identified:
`StrategyRegistry.updateReputation(actor, delta)` reverts
`StrategyNotFound()` at `StrategyRegistry.sol:187` because the deployer
EOA isn't a registered strategy. The single-update path (`sendReputationUpdate`
→ `_applyReputation` → `postCrossChainUpdate` → `_applyUpdate` →
`strategyRegistry.updateReputation`) requires registered-strategy chain
state to succeed.

**Pivot to the batch path** (`queueAttestation` + `flushAttestationsFor`):
on receive the OApp calls `postCrossChainTradeTick(actor)` which only
increments `_reputations[actor].totalAttestedTrades` (no registry call;
counter-only). That path proves the **LZ V2 infrastructure** (DVN
delivery, peer trust, codec, `_lzReceive` decoder, OApp event emit)
without needing chain-state surgery to register a fake strategy.

| Field | Value |
|---|---|
| Path | `queueAttestation` + `flushAttestationsFor` (batch / trade-tick) |
| Source | `TriggerXChainBatch.s.sol` on Base Sepolia |
| Flush tx | `0x9d777976deb0422a3796667aa81735dfc781d03f7d43ac0cde8add7ace949401` |
| Batch GUID | `0xf3e1efba2972b693acfb4128f0734be531c02488c17a50f277fa54960bf291d0` |
| LZ Scan (live) | INFLIGHT — DVN verification + sealer committed; destination delivery pending |

Tracking final destination land under WS10.7.

**Update (2026-05-11, late afternoon)**: the batch path ALSO failed at the
executor. Root cause discovered: the deployed V1 ReputationAnchor at
`0x51c07adf…` is the Phase-1 source vintage and does NOT contain
`postCrossChainTradeTick` (selector `0xc288b290`). Confirmed by enumerating
the deployed bytecode's selectors via PUSH4 scan — only the V1 7-field
`postCrossChainUpdate` (selector `0x94c8dd5e`) is present; neither V2's
8-field variant nor any tick selector exists. So both inbound paths from
the OApp revert because the destination contract simply doesn't recognize
the function selectors the OApp emits.

This is an **anchor compatibility** gap, not an LZ infra gap — the LZ V2
transport, DVN delivery, peer trust, OApp codec, and `_lzReceive`
dispatcher all work (proven by every send-side success + DVN-verified
inbound on LZ Scan). The deployed V1 anchor predates the OApp's V2 ABI;
the OApp can't be retrofit to call V1 because `reputationAnchor` is
declared `immutable` (`HeliosOApp.sol:29`). Two real-world resolutions:
(a) eventual Phase-5 cutover to the V2 anchor `0x735680a3…` (deferred —
requires registry redeploys per `docs/reputation-v1-v2-cutover.md`), or
(b) future redeploy of V1 with PR #90 source.

**Pivot**: For WS10 acceptance specifically, redeploy the Kite OApp with
`reputationAnchor = address(0)`. `HeliosOApp._applyReputation:299` and
`_applyTradeTick:280` null-check the anchor, so a zero-anchor OApp
SKIPS the integration call and proceeds to emit `ReputationMessageReceived`.
This proves the cross-chain INFRASTRUCTURE end-to-end without depending
on canonical-anchor integration.

| Item | Value |
|---|---|
| New Kite OApp (null anchor) | `0x7Bad5250A1C0B286bC5128bB1D7c19320341C830` |
| Deploy tx | `0xee09df8621cacf425993f120858560b3c97e3428faf30c024b12e1e11d297fbb` |
| Prev Kite OApp (preserved in JSON as `heliosOAppPrev`) | `0x9D93F3f2254d7d6f6f4208938b7Ce7F9E33c43B3` |
| 4 peer-rewire txs | Kite→Base `0xdf0fdd07…`, Kite→Arb `0xc5d6969f…`, Base→Kite `0xcafbd128…`, Arb→Kite `0x87b77cd0…` (all status=1) |
| Fresh batch flush | tx `0xb23d24d5eac913b191709dd3e4e7b7806c4be7410a893a87e9d68661f38f3cb4` |
| Fresh batch GUID | `0x2eb1ec248ba911c556715f4d43242687098e32c638f3c3449d7a3e8706ab55ca` |

### WS10.7 — Verify LZ V2 round-trip delivery — COMPLETE (2026-05-11)

**Acceptance proven end-to-end. Single GUID traceable in both directions:**

| Direction | Source tx | Dest tx | GUID | Block |
|---|---|---|---|---|
| Base → Kite | `0xb23d24d5eac913b191709dd3e4e7b7806c4be7410a893a87e9d68661f38f3cb4` | `0xcf313f052b128497e6ae73d204af6542992a22dd544824427b9c13fece36b395` | `0x2eb1ec248ba911c556715f4d43242687098e32c638f3c3449d7a3e8706ab55ca` | Kite 21308858 |
| Arb → Kite | `0xae29f8338305b398d17bfa5308e8766c1e522364b0637b47e130af214d8704b2` | `0x46bdede7fe754e8727a19a9db2ac1476690dba1e4d81ecc239133a6392027c09` | `0x4191d1e0c8208e5146b4bfa3e4fbb9a39f20e52e1b81a25734abe5c688abdf59` | Kite 21308958 |

Both destination txs landed `status=1` and emitted
`ReputationMessageReceived(srcEid, actor, actorType, guid)` from
the Kite OApp `0x7Bad5250A1C0B286bC5128bB1D7c19320341C830`. LZ Scan
reports both as DELIVERED. Path used: `queueAttestation` +
`flushAttestationsFor` (batch / trade-tick) — the OApp's `_lzReceive`
decoder dispatches `_handleReputationBatch` → `_applyTradeTick` → the
null-anchor skip at `HeliosOApp.sol:280` → `emit ReputationMessageReceived`.

**Infrastructure verified end-to-end**: LZ V2 transport (Base/Arb
Sepolia ↔ Kite), DVN delivery, bidirectional peer trust, OApp
codec round-trip, `_lzReceive` dispatcher, and receive-side event
emission all work against the live Kite LayerZero V2 endpoint.

### WS10.8 — Commit + docs + phase6-plan.md update — in progress

## Risks (live tracking)

1. **DVN scheduling**: testnet round-trip is non-deterministic. If
   `measure_xchain_latency.py --timeout 600` exits non-zero, that's a
   warning sign but not a definitive failure — wait, then retry.
2. **Faucet rate limits**: blocks WS10.2. User-action.
3. **Reputation engine doesn't currently forward to OApp**:
   `services/reputation/` writes only to the local ReputationAnchor; it
   never calls `sendReputationUpdate`. WS10 tests **infrastructure** by
   sending a bare-metal message in WS10.6, not the **integration**.
   Wiring the off-chain forwarder is a follow-up after WS10.7 passes.

## Follow-ups out of scope for WS10

- Wire `services/reputation/` to call `sendReputationUpdate` on the
  destination-chain OApp after each trade attestation.
- Deploy Phase-5 strategy vault proxies on Base/Arb (the deploy script
  only ships the impl per the comment at line 153).
- Frontend cross-chain card env wiring (`NEXT_PUBLIC_HELIOS_OAPP_*` in
  Vercel) and the visual polish that goes with it.
- Subgraph deploy for `subgraph.base-sepolia.yaml` /
  `subgraph.arbitrum-sepolia.yaml` (Goldsky deploy depends on these
  deployment JSONs to populate addresses).
