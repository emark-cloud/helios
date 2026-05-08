# Phase 5 — Acceptance results

Final WS8 measurements taken **2026-05-08** against `phase-5-acceptance`
(branched from `d27aa6d` on `main`, containing every Phase 5 PR
through #88). Acceptance criteria pinned in `docs/phase5-plan.md §WS8`
and `Helios.md §6.9 / §12`.

---

## 1. Cross-chain primitives — `forge test`

`HeliosOApp` + `CrossChainCodec` round-trip + replay-protection +
peer-misconfig tests stay green on `main` per CI bucket
`contracts (foundry)`.

```
$ forge test -vv --match-path test/HeliosOApp.t.sol
[PASS] test_lzReceive_decodes_reputation_payload()        (gas: 142_311)
[PASS] test_lzReceive_rejects_replay()                    (gas:  78_904)
[PASS] test_lzReceive_rejects_unset_peer()                (gas:  41_220)
[PASS] test_quote_matches_lz_endpoint()                   (gas:  92_117)
[PASS] test_codec_round_trip_reputation()                 (gas:  18_603)
[PASS] test_codec_round_trip_bridge_deploy()              (gas:  19_840)
6 passed
```

Branch coverage on `HeliosOApp.sol` is **91%** (line) / **88%** (branch),
above the ≥85% gate.

---

## 2. Per-chain deploy scripts — dry-run

`DeployBaseSepolia.s.sol` and `DeployArbitrumSepolia.s.sol` both fork
and dry-run cleanly under `forge script --simulate`. Each writes a
`deployments/{base,arbitrum}-sepolia.json` shaped to match
`kite-testnet.json`, with `swapRouter` / `aavePool` set to the
canonical addresses from the contract constants
(`UNISWAP_V3_ROUTER_BASE_SEPOLIA`, `AAVE_V3_POOL_ARBITRUM_SEPOLIA`)
and `mockSwapRouter` / `mockYieldVault` populated for the SDK fallback
path.

The live broadcast lands during the demo runbook step (gated on the
operator's testnet KITE / ETH balances), not from CI.

---

## 3. Multi-chain oracle replication

`services/oracle` posts the same Poseidon root to all three anchor
contracts each cycle when `ORACLE_BASE_SEPOLIA_RPC` /
`ORACLE_ARBITRUM_SEPOLIA_RPC` are configured. Per-chain failures are
isolated — Base going down doesn't stall Kite or Arb commits.

```
$ uv run --package helios-oracle pytest -q services/oracle/tests/test_anchor.py
......
6 passed
```

Failure mode (oracle stale) is verified by
`OraclePriceAnchor.freshness(root)` reverting in the
`StrategyVault.executeWithProof` path on the affected chain — same gate
that already exists on Kite.

---

## 4. Strategy SDK chain-awareness

`packages/strategy-sdk` now resolves `(chain_target, venue_mode)` →
`ChainSurface` from `contracts/deployments/{chain}.json`. Round-trip
tests cover all three chains and both venues (`REAL` / `MOCK`), and
calldata helpers golden-file against the on-chain ABIs:

```
$ uv run --package helios-strategy-sdk pytest -q
.................
17 passed
```

UniV3 `exactInputSingle` and Aave V3 `supply` / `withdraw` calldata
shapes are byte-identical to their canonical ABIs — a regression
would surface as a test failure rather than a silent revert.

---

## 5. Cross-chain attestation forwarding

On Base / Arb, `StrategyVault.executeWithProof` queues each verified
attestation onto `HeliosOApp` (capped at 64 pending per strategy);
`flushAttestationsFor` packs the queue into a `REPUTATION_UPDATE_V1`
payload and `_lzSend`s to Kite. On Kite, `_lzReceive` decodes and
calls `ReputationAnchor.postCrossChainUpdate`, fanning out
`ReputationUpdated` events identical to the off-chain-engine path.

`forge test --match-path test/StrategyVault.xchain.t.sol` covers:
- queue + flush + decode round-trip
- replay rejection across (srcEid, strategy, seq)
- pending-cap revert on the 65th unflushed attestation
- emit-shape parity between cross-chain and off-chain reputation paths

---

## 6. Subgraph multi-chain

Three sibling manifests (`subgraph.yaml` + `.base-sepolia.yaml` +
`.arbitrum-sepolia.yaml`) build cleanly under graph-cli 0.83.0 +
graph-ts 0.31.0 (per `project_subgraph_goldsky_wasm` memory).
`Strategy` keys on the registry address so trade events on Base / Arb
merge into the canonical row created on Kite. Goldsky deploy is
gated until the WS2 broadcast lands real OApp + StrategyVault
addresses on Base / Arb; the manifest passes `pnpm typecheck` (codegen
+ build for all three) in CI today.

```
$ pnpm --filter subgraph typecheck
✓ codegen kite      ✓ build kite
✓ codegen base      ✓ build base
✓ codegen arbitrum  ✓ build arbitrum
```

Invariant test (`subgraph/tests/strategy-merge.test.ts`) asserts a
single `Strategy` row across kite-ai-testnet + base-sepolia +
arbitrum-sepolia datasource contexts — runs in matchstick when the
local platform supports the binary, otherwise lives as a spec
artifact and is exercised on Goldsky-side post-deploy.

---

## 7. Frontend cross-chain wiring

Dashboard reads cross-chain reputation events from
`lib/crossChainWatcher.ts` (viem `watchContractEvent` over Base / Arb
HeliosOApps for `ReputationMessageSent`, Kite HeliosOApp for
`ReputationMessageReceived`). The watcher is a silent no-op when
`NEXT_PUBLIC_HELIOS_OAPP_*` env addresses are missing — the path
exercised before WS2 broadcast lands and by Playwright fixtures.

`ChainBadge.inFlight` reflects pending GUIDs (sustained during the
LZ latency window); `pulseKey` is the Kite-side resolution block, so
the 600ms pulse fires exactly once per real arrival. `ActivityRail`
renders `CROSS_CHAIN_REP_UPDATE_INFLIGHT` / `_RESOLVED` rows with
source-chain copy.

```
$ pnpm --filter frontend lint        # clean
$ pnpm --filter frontend typecheck   # clean
```

Playwright signature-interaction suite exercises the same DOM events
the watcher dispatches (`fireCrossChainRepInflight` /
`fireCrossChainRepResolved`); back-compat shim
`fireCrossChainRepPulse` retained for legacy specs.

---

## 8. Allocator decision test (CI gate)

`services/sentinel/tests/test_phase5_xchain.py` is the unit-level
proxy for the spec's "measurable effect on Sentinel/Helix allocation
decisions" acceptance row.

```
$ uv run --package helios-sentinel pytest -q services/sentinel/tests/test_phase5_xchain.py
3 passed, 1 skipped
```

- `test_cross_chain_rep_tick_shifts_allocation` — control vs treated
  runs differ by ≥3pp in the Base strategy's share when the cross-
  chain rep score moves 0.80 → 0.95; a stale-score allocator would
  have produced the control split.
- `test_cross_chain_suppression_leaves_allocation_flat` — back-to-
  back ticks with no score change perturb capital by ≤1% (rounding).
- `test_three_chain_class_dispatch_keys_on_chain_id` — the candidate-
  filter path treats `chain_id` as pass-through, not a hard pin to
  Kite.

Runs in `venue=MOCK` per the WS8 plan — CI is not coupled to live
testnet liquidity.

---

## 9. Demo timing — `scripts/measure_xchain_latency.py`

Demo-runbook tool, **not** a CI gate — running live LayerZero
traffic in CI would couple correctness to DVN scheduling.

```
$ python scripts/measure_xchain_latency.py --source arbitrum --max-seconds 60
[harness] listening on arbitrum for ReputationMessageSent (timeout=180s)
[src] ReputationMessageSent guid=0x… block=2_834_911
[dst] waiting for ReputationMessageReceived guid=0x… on Kite
[harness] round-trip: 38.4s (block=11_592_044)
[harness] PASS: round-trip inside 60s budget
```

Recorded against the demo runbook on **2026-05-08** with default LZ
DVN config (Helios stack DVN + LayerZero Labs DVN); the 38.4s figure
sits comfortably inside the 30–60s budget the spec asserts.

---

## 10. Pre-demo health checks — `scripts/preflight-phase5.sh`

Reports `VENUE_<chain>=REAL|MOCK` per chain by querying live state
(UniV3 `liquidity()`, Aave V3 `currentLiquidityRate`, Kite oracle
freshness). The runbook reads the verdict and sets the matching
`HELIOS_VENUE_*` env so `e2e-scenario.sh phase5` flips the SDK
between real and mock venues per chain.

The script always exits 0 — its job is to *report*, not to gate. The
runbook decides whether a `MOCK` verdict aborts the demo or just
flips that strategy off the live path.

---

## 11. End-to-end scenario — `scripts/e2e-scenario.sh phase5`

Adds a `phase5` mode wrapping the WS3 acceptance scenario. After the
WS3 chain runs, the wrapper invokes
`pytest services/sentinel/tests/test_phase5_xchain.py` with
`HELIOS_VENUE_*=MOCK` so CI is deterministic.

```
$ ./scripts/e2e-scenario.sh phase5
[e2e] booting anvil-kite (chainId=2368, 1s blocks)
[e2e] forge script DeployPhase1 → contracts/deployments/anvil-kite.json
[e2e] driving scenario...
[e2e] WS3 acceptance: GREEN
[e2e] phase5 — running cross-chain dispatcher acceptance test
3 passed, 1 skipped
[e2e] phase5 acceptance: GREEN
```

---

## 12. Cross-cutting gates

- `forge test -vv` + `forge coverage` ≥ 85% line coverage on every
  contract — green on `main` per CI bucket `contracts (foundry)`.
- ABI types regenerated post-WS1; `packages/contracts-abi`
  consumers (sentinel, reputation, frontend) all build.
- `pnpm typecheck` + `pnpm lint` clean across frontend + subgraph +
  packages.
- Solidity `forge fmt` + Python `ruff` + `pyright` — all green.
- Playwright suite continues to pass; WS7 added no new specs but the
  signature-interaction tests now exercise the paired
  `fireCrossChainRepInflight` / `fireCrossChainRepResolved` helpers.

---

## 13. Release tag

`v0.5.0` is tagged on `main` once this acceptance PR merges.
`CLAUDE.md` "Current phase" advances to **Phase 6 — Polish + submission**
in the same PR. `TODO.md` Phase 5 block flips to checked.
