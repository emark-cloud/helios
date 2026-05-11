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

### WS10.1 — Existing test baseline — _pending_

### WS10.2 — Env + faucet on Base/Arb Sepolia — _pending (user-action)_

The deployer EOA (`0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25`) needs
~0.1 ETH on each of Base Sepolia and Arbitrum Sepolia. Faucets:

- https://www.alchemy.com/faucets/base-sepolia
- https://www.alchemy.com/faucets/arbitrum-sepolia

Env entries to add to local `.env` (not committed):

```
BASE_SEPOLIA_RPC_URL=<infura/alchemy URL>
ARBITRUM_SEPOLIA_RPC_URL=<infura/alchemy URL>
LZ_ENDPOINT_BASE_SEPOLIA=0x6EDCE65403992e310A62460808c4b910D972f10f
LZ_ENDPOINT_ARBITRUM_SEPOLIA=0x6EDCE65403992e310A62460808c4b910D972f10f
LZ_ENDPOINT_KITE=0x3aCAAf60502791D199a5a5F0B173D78229eBFe32
LZ_KITE_EID=40415
LZ_BASE_SEPOLIA_EID=40245
LZ_ARBITRUM_SEPOLIA_EID=40231
```

### WS10.3 — Kite-side HeliosOApp deploy script — _pending_

Need `contracts/script/DeployKiteHeliosOApp.s.sol` modelled on
DeployPhase5Execution but with `reputationAnchor_ =
0x51c07adf596b1e72697a9b8232d061ed006943dc` (the live V1 anchor),
NOT `address(0)`. Persists `heliosOApp` + `lzKiteEid` into
`kite-testnet.json`.

### WS10.4 — Broadcast — _pending_

### WS10.5 — Wire peers — _pending_

### WS10.6 — Send — _pending_

### WS10.7 — Verify round-trip — _pending_

### WS10.8 — Commit + docs — _pending_

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
