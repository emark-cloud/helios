# Phase 6 — Polish + submission plan

> **Source of truth:** `TODO.md` Phase 6 block; `DESIGN.md §9.7-§9.8, §13`; `Helios.md §15, §19`.

## Context

Phases 0–5 complete as of 2026-05-08; `v0.5.0` tagged on `main`. The Phase-6 real-price cutover (full plan in `docs/phase6-realprice-plan.md`) landed 2026-05-09 and is tagged `v0.6.0-realprice` at commit `0034fb4` — nine fresh multi-asset StrategyVaults active on Kite testnet, the legacy nine flipped to `active=false` in `StrategyRegistry`, and a `RouterPriceMirror` keeper inside `services/oracle` feeding live BTC/ETH/SOL prices into `MockSwapRouter` so NAV moves with the market. Phase 6 from here is judge-readiness + defensibility under scrutiny on that stack. Mainnet promotion stays in the Stretch section (`TODO.md` line 506) — exercised only if time remains.

What's already in place coming into Phase 6:
- `/judge` and `/audit/[strategy]` shipped in Phase 4 (WS-FE-2, WS-FE-4)
- PM2 ecosystem (`deploy/ecosystem.config.cjs`) + Nginx reverse proxy (`deploy/nginx/helios.conf`) + TLS bootstrap (`deploy/setup-tls.sh`)
- Backtest reports for all three strategy classes (`docs/backtests/*.md`)
- `docs/reputation-math.md`, `docs/operator-guide.md`

What's missing (the Phase 6 work):
- `scripts/verify-trade.js` standalone Groth16 re-verifier
- Slither / Mythril CI; triage doc for findings
- Threat model rendered as standalone doc; allocator + circuit specs
- README rewrite (judge-friendly entry, "Reproduce in 5 min", rate-limits subsection)
- Nginx rate limits tuned to spec (100 r/min reads, 10 r/min writes — current values are an order of magnitude looser)
- Demo materials: 3-min live script, 90-sec backup video, cold-start runbook
- VPS pre-deploy ≥48 h before judging deadline

## Workstream order

### WS1 — FE polish + verify-trade script
- **WS1.A** — `scripts/verify-trade.js`: single-file Node ESM, deps `ethers@^6` only. Reads tx receipt → decodes `executeWithProof` calldata for the proof bytes → reads `TAV.verifierByClassMap(declaredClass)` → calls `verifyProof(a, b, c, publicInputs)` and prints PASS/FAIL.
- **WS1.B** — `/judge` + `/audit/[strategy]` audit against `DESIGN.md §9.7-9.8, §4.3, §13`. Read-only review producing a punch list.
- **WS1.B-followups** — fix the blockers and polish items the audit surfaces (Goldsky placeholder leak, dead Vimeo links, marketing-adjacent copy, motion-budget exceptions, hardcoded RPC/explorer host, pagination math, stale "Phase 5/6 reserved" rows).

### WS2 — Security passes
- **WS2.A** — `.github/workflows/security.yml` running Slither (informational, `fail-on: none`) on every PR + manual dispatch. Mythril stubbed with a documented run procedure. `docs/audit-checklist.md` pre-filled with first Slither run findings (severity / status / mitigation).
- **WS2.B** — `docs/threat-model.md`: render `Helios.md §15.2` with a per-row "test or mitigation" column. Reference contracts/tests verbatim with file:line.
- Circuit unit-test audit (zero/max/boundary coverage) is pulled from the Phase 6 list as a sub-task once WS2.A lands and we know what coverage gaps Slither flags.

### WS3 — Deploy hardening
- **Tune Nginx rate limits to spec.** Current zones (`helios_default 20 r/s`, `helios_prover 4 r/s`, `helios_dashboard 10 r/s`) are looser than the Phase 6 spec (100 r/min reads, 10 r/min writes). Convert to per-minute zones, split read vs write routes, document values in `deploy/README.md`. **Sync edit:** `docs/threat-model.md` rate-limit row needs the new values once these land.
- Health-check endpoints + PM2 log-rotation + email digest for restart events.
- Postgres backup cron (`deploy/postgres-backup.sh`) + restore runbook in `deploy/README.md`.
- Secrets audit: confirm `/srv/helios/.env` is the only place secrets land.
- Calendar item: VPS pre-deploy ≥ 48 h before deadline (no code change; runbook in `deploy/README.md`).

### WS4 — Docs (depends on WS2 outputs)
- `docs/allocator-guide.md` (mirror `operator-guide.md` structure).
- `docs/circuit-specs.md` (per-class invariants from `Helios.md §9`).
- `docs/threat-model.md` — already from WS2.B.
- `docs/audit-checklist.md` — already from WS2.A.
- README rewrite: judge-friendly entry, repo map link, demo video link, live URL, `/judge` link, "Reproduce the demo in 5 minutes" block, "Rate limits & scoped permissions" subsection (per-strategy cap, Nginx values, `min_bar_interval`).

### WS5 — Demo (depends on WS5-prep + WS9)
- **WS5-prep** — trigger ≥ 1 attested trade on Kite testnet against the **Phase-6 multi-asset vaults** (the 2026-05-08 vaults are now `active=false`). `verify-trade.js` has no PASS smoke target until a real `executeWithProof` lands on one of `phase6Vault*` (`docs/active-strategies.md`). **WS5-prep prerequisites already met (2026-05-10)**: VPS compose stack live, Vercel frontend live with the decimals + slug → bytes32 + USD-scaling fixes, user-side onboarding completed, allocator's `allocateToStrategy` calls landed (5×33.33 mUSDC across `phase6Vault*` + topped up to 9 active allocations after sentinel rebuild). Now blocked on **WS9** — the strategy-runtime side has never fired a `TradeAttested` event because of seven cascading misconfigs documented in WS9 below.
- 3-minute live demo script (markdown checklist in `docs/demo-runbook.md`).
- 90-second backup video + hosted URL linked from `/judge` and README.
- Cold-start verification: fresh-clone → `pnpm install && uv sync && forge install && pnpm dev` → `scripts/e2e-scenario.sh` finishes within 10 minutes. Document the timing.

### WS9 — Autonomous attested trades (gates WS5)
Make the deployed strategy services fire `TradeAttested` events on every bar where a class signal exceeds threshold, no script and no manual intervention. Detailed plan + verification criteria in `/home/emark/.claude/plans/dazzling-spinning-quokka.md`. Three layers:

- **L1 — Oracle.** Add `WBTC→BTC/USDT`, `WETH→ETH/USDT`, `WSOL→SOL/USDT` aliases at the route layer in `services/oracle/src/oracle/service.py` so the strategies stop getting 404s. Tighten `ORACLE_ANCHOR_INTERVAL_BARS` to `1` (default `50`) so the latest committed root is always inside the 180s freshness budget at `StrategyVault._validateAndVerify`.
- **L2 — Strategy services (all three classes).** (a) Wire `*_ASSET_UNIVERSE_ADDRESSES_JSON` env → runtime constructor (today the runtime falls back to symbols + 4 empty strings, witness can't resolve indices for the deployed 4-asset universe). (b) Replace `_DummyBlockProvider` with a `Web3BlockProvider` that reads `w3.eth.block_number` so the witness's `block_window_start/end` aligns with the live chain. (c) Lifespan hook computes `Poseidon(operator-bounds)` and calls `StrategyRegistry.commitInitialParamsHash(vault, hash)` idempotently on first boot — no service has ever done this for any of the 9 vaults, so every prior `executeWithProof` would have reverted `ParamsHashMismatch` even with everything else green. Hash field order per class: momentum `[max_position_size_e18, max_slippage_bps, signal_threshold_bps, stop_loss_price_e18]`, mean-reversion `[…, n_sigma_x100, …]`, yield-rotation `[signal_threshold_bps, bridging_cost_bps]`. Shared helper lives in `packages/strategy-sdk/src/helios/runtime/registry_init.py`.
- **L3 — VPS bring-up.** Update `/srv/helios/.env` with `*_OPERATOR_PK = $DEPLOYER_PK`, `NAV_ORACLE_PK = $DEPLOYER_PK`, the `*_ASSET_UNIVERSE_ADDRESSES_JSON` payloads, the per-class `*_STRATEGY_VAULT_ADDRESS` (the `.base` variant per class — the other 6 are explicitly future work), `ALLOCATOR_ADDRESS`, and `*_ASSET_DECIMALS_JSON`. `git pull && docker compose up -d --force-recreate oracle momentum_v1 mean_reversion_v1 yield_rotation_v1`. The strategies' lifespan hook commits paramsHash on boot; after ~16 bars warm-up the bar loop fires real trades.

**Out of scope (future work, filed below):** wiring the other 6 vaults (`variant2`/`variant3` per class), and bullet-proofing the strategy → committed-anchor-root alignment so it's >99% match instead of ~95%.

### WS10 — Cross-chain (LayerZero V2) verification

Phase 5 shipped the cross-chain Solidity primitives (`contracts/src/HeliosOApp.sol`, deploy + peer-wire scripts, the `measure_xchain_latency.py` harness) and unit-level test coverage (`contracts/test/HeliosOApp.t.sol` 6/6 forge tests pass, `services/sentinel/tests/test_phase5_xchain.py` covers the allocator cascade with a mocked LZ endpoint). What never happened: `DeployPhase5Execution.s.sol` was never broadcast on any chain, no `setPeer` call has landed, and the Kite-side OApp has no deploy script (the existing one is Base/Arb-only, hardcodes `reputationAnchor=address(0)`). WS10 deploys the missing infrastructure and proves a real LayerZero V2 message round-trip against testnet.

Live tracking + evidence log in `docs/phase5-xchain-verification.md`. Pre-check (2026-05-11) confirmed Kite testnet IS on LZ V2 (EndpointV2 `0x3aCAAf60502791D199a5a5F0B173D78229eBFe32`, EID `40415`), so the full 3-chain round-trip is viable. Detailed plan in `/home/emark/.claude/plans/dazzling-spinning-quokka.md`. Eight sub-steps: baseline existing tests → user-action faucet on Base/Arb → write `DeployKiteHeliosOApp.s.sol` → broadcast on three chains → wire peers bidirectionally → trigger a `sendReputationUpdate` from Base → confirm `ReputationMessageReceived` on Kite via `measure_xchain_latency.py` → commit deployment JSONs + docs + `CLAUDE.md` Phase 5 address block.

**Acceptance**: a single GUID traceable from `ReputationMessageSent` on a source chain to `ReputationMessageReceived` on Kite within 60s, plus regression on the existing unit suite.

**Out of scope (follow-ups after WS10.7 passes):** wiring `services/reputation/` to call `sendReputationUpdate` on the destination OApp after each trade attestation (the engine currently writes only to the local anchor); deploying Phase-5 strategy vault proxies on Base/Arb (DeployPhase5Execution ships the impl but not the proxies); Goldsky deploy for `subgraph.base-sepolia.yaml` / `subgraph.arbitrum-sepolia.yaml`; frontend cross-chain card env wiring on Vercel.

### WS6 — Phase 6 acceptance + tag (gated on everything)
- Cold-judge dry run: 5-step `/judge` checklist completes in under 5 minutes, including independent ZK verify.
- Slither/Mythril clean (or every finding documented).
- `v0.5.0` (Phase 5 cross-chain) and `v0.6.0-realprice` (multi-asset cutover) are already on `main`. Cut `v1.0.0` once the cold-judge dry run + WS5 demo materials land against the Phase-6 vault set.

## Parallelism

- WS1 and WS2 are independent; kicked off in parallel via four agents (WS1.A, WS1.B, WS2.A, WS2.B). All four complete.
- WS1.B-followups is unblocked by WS1.A (script existence removes the modal "Phase status" disclaimer; followups also batch with the script-shape change in `/judge` `VerifyBlock`).
- WS3 and WS4 can largely run in parallel; the threat-model rate-limit row is the only cross-WS sync edit.
- WS5 sits behind WS5-prep (need a real attested-trade tx hash to demo).
- WS6 gates on all of the above.

## Acceptance for Phase 6

Mirrors `TODO.md` lines 497–502:
- A cold judge following `/judge`'s 5-step checklist completes evaluation in under 5 minutes.
- Judge can verify a ZK proof independently against an on-chain tx and confirm it matches.
- Slither/Mythril all pass (or every finding documented + justified).
- Cold-start demo succeeds on a machine that has never touched the repo before.
- Backup video is uploaded and linked.

## Status snapshot (2026-05-09, end of day)

| Track | Status |
|---|---|
| WS1.A — verify-trade.js | ✅ written; PASS smoke pending WS5-prep on Phase-6 vaults |
| WS1.B — /judge + /audit audit | ✅ punch list returned |
| WS1.B-followups | ✅ all FE blockers fixed; typecheck + lint clean |
| WS2.A — Slither CI + audit-checklist | ✅ workflow + 9H/27M/57L/227I triage doc; all 9H are known false positives in snarkjs-generated verifiers |
| WS2.B — threat-model doc | ✅ 14 rows, 10 mitigated / 4 accepted |
| WS3 — Deploy hardening | ✅ Nginx tuned to spec (100/min reads, 10/min writes, 5/min prover); postgres-backup.sh + restore runbook; deploy/README.md expanded; secrets audit clean |
| WS4 — Docs (allocator, circuit-specs, README) | ✅ allocator-guide 631L; circuit-specs 555L; README rewritten |
| #11 — Circuit test coverage gaps | ✅ 7 new tests; 58/58 passing |
| #12 — Allocator-init scaffold fix | ✅ template rewritten; verified end-to-end with real install + boot |
| #13 — Circuit zero-amount reject (mom + MR) | ✅ **fully closed (repo + chain) 2026-05-08**. Circuits add Constraint 0 (`Num2Bits(128)` on `amount_in - 1`); artifacts regenerated (43/43 circuit + 394/395 forge + 10/10 prover); new TAV `0x3698F60a…` deployed with PR #70 timelock code (the legacy testnet TAV at `0x743e1bd7…` was the lax pre-PR-#70 version with no rotation path, so a heavy redeploy + UUPS upgrade was the only viable path); new mom + MR verifier+adapters; new `StrategyVault` impl `0x934f7639…` adds `migrateVerifier(reinitializer(2))`; all 9 vault proxies upgrade-and-call'd to the new TAV in one tx each. JSON + CLAUDE.md updated. |
| **Real-price cutover (`docs/phase6-realprice-plan.md`)** | ✅ **fully shipped 2026-05-09, tagged `v0.6.0-realprice`**. Multi-asset universe `[mUSDC, mWBTC, mWETH, mSOL]` (mom/mr) + `[mUSDC]` (yr) live; nine fresh `phase6Vault*` proxies on impl `0x934f7639…` with per-(class,variant) `paramsHash`; legacy nine deactivated; `MockSwapRouter` seeded with synthetic inventory; `RouterPriceMirror` keeper in `services/oracle` mirrors signed snapshots into `setPrice` each bar; `momentum_v1`/`mean_reversion_v1` witness builders threaded with per-asset decimals; Goldsky subgraph redeployed at `helios/v0.6.0`; `scripts/e2e-scenario.sh phase6-realprice` green; `docs/active-strategies.md` records the cutover; CLAUDE.md addresses block refreshed. |
| WS5-prep — Passport sign-in unblock | ✅ three stacked SDK fixes 2026-05-09 — `process/browser` aliased to `frontend/process-shim.cjs` (Particle pino logger's `isTTY` read), `chainName: "Gokite"` (so Particle resolves the `gokite-2368` chain key registered by `@gokite-network/auth`), `kite_testnet` underscore (gokite-aa-sdk's `NETWORKS` map keys). Sign-in flow now reaches userOp build. |
| WS5-prep — VPS operator runtime | ✅ first-time VPS deploy 2026-05-09 — postgres, redis, prover, sentinel, reputation, oracle, momentum_v1 + mean_reversion_v1 + yield_rotation_v1 all up under compose; oracle anchoring real prices on-chain; `RouterPriceMirror` enabled (env `ROUTER_MIRROR_ENABLED=1`); 6 bring-up bugs fixed in flight (uvicorn reload, WKITE/WETH alias, coingecko `kite-2` slug, `root_bytes32` decode, node-Dockerfile UID collision, oracle Poseidon node install). |
| WS5-prep — frontend on Vercel | ✅ live at `helios-frontend-steel.vercel.app`; reads `phase6Vault*` addresses from regenerated `kite-testnet.json`; Passport credentials wired. |
| WS5-prep — testnet onboarding | ✅ user onboarded 2026-05-10; allocator's `allocateToStrategy` landed 5×33.33 mUSDC plus subsequent top-ups (9 active allocations). Sentinel decimals fix shipped, dashboard reads in human-readable USD. |
| WS9 — Autonomous attested trades | ⏳ in progress 2026-05-10; seven blockers identified across oracle aliases, anchor cadence, asset_universe_addresses wiring, BlockProvider, paramsHash commit, operator/NAV signing keys. Plan: `/home/emark/.claude/plans/dazzling-spinning-quokka.md`. |
| WS5 — Demo materials | ⏳ gated on WS9 — first `TradeAttested` event needed before `verify-trade.js` PASS smoke + demo script can finalize. |
| WS6 — Acceptance + tag | ⏳ gated on WS5; will cut `v1.0.0` once cold-judge dry run passes against the Phase-6 vault set. |
| #17 — Reputation V1 `InvalidSigner` revert | ⏳ tracked; not demo-blocking — V2 sidecar is what `/audit` reads. |
| #18 — VPS pm2 systemd unit + nginx swap | ⏳ deferred; needs sudo password from user. |
| **WS10 — Cross-chain (LayerZero V2) verification** | ✅ infrastructure verified end-to-end 2026-05-11. Both Base→Kite (GUID `0x2eb1ec24…`, dest tx `0xcf313f05…`) and Arb→Kite (GUID `0x4191d1e0…`, dest tx `0x46bdede7…`) emit `ReputationMessageReceived` on Kite OApp `0x7bad5250…`. Surfaced + documented a separate integration gap: the V1 ReputationAnchor (Phase-1 vintage) predates the OApp's V2 ABI for `postCrossChainTradeTick` + 8-field `postCrossChainUpdate` selectors — the WS10 verification OApp uses `reputationAnchor=address(0)` to skip the integration call; full anchor integration is a Phase-5 V1→V2 cutover follow-up (see `docs/reputation-v1-v2-cutover.md`). Evidence: `docs/phase5-xchain-verification.md`. |

## Open items from before WS10 (parked, not lost)

WS10 is the active focus; these stay tracked so they don't slip:

- **#40 — Verify autonomous trade firing on Kite testnet** — `bkcs56cvt` monitor timed out waiting for the first mr `executeWithProof` post-`CommitMirror`. No new exec since. Re-arm or wait for next high-volatility window; closure proves the WS9 chain end-to-end.
- **#50 — Oracle `CommitMirror` verification** — deployed to `services/oracle/src/oracle/commit_mirror.py` + wired into the snapshots HTTP views, but the "did it actually fix `UnknownOracleRoot`?" question only closes when an mr exec lands as `TradeAttested`. Shares the gate with #40.
- **#10 — WS5-prep: real attested trade on Kite testnet** — gated on #40. `verify-trade.js` PASS-smoke needs a real on-chain `executeWithProof` against one of the `phase6Vault*` proxies.
- **#7 — WS5 Demo materials** — user-directed to be last priority; gated on #10.
- **#8 — WS6 Phase 6 acceptance + `v1.0.0` tag** — gated on #7 + cold-judge dry run.
- **WS9 latent follow-ups** — stranded NAV in the deactivated `mom.legacy` cohort and cold-start ranking parity (project memory `project_sentinel_allocation_gap.md`); not formal tasks, picked up opportunistically.

## Newly-uncovered work (during Phase 6)

- **Real-price cutover (2026-05-09)**: WS5-prep on the 2026-05-08 vaults exposed that every StrategyVault's `assetUniverse = [mUSDC]` left strategies with nothing to swap to — trades no-op'd and NAV was structurally flat, so a "successful" attested trade still wouldn't move the demo numbers. Surgical fix landed as a self-contained workstream (`docs/phase6-realprice-plan.md`) over commits `52c7645`…`0034fb4`: deployed mWBTC/mWETH/mSOL `MockERC20`s, seeded `MockSwapRouter` inventory, registered nine fresh multi-asset vaults via `DeployPhase6MultiAssetVaults.s.sol`, deactivated the legacy nine via `DeactivateLegacyVaults.s.sol`, added `RouterPriceMirror` to `services/oracle` (`services/oracle/src/oracle/router_mirror.py` + `_math.py`) reusing `Poller.on_snapshot` + `AnchorPoster` plumbing, threaded `asset_decimals` through the reference-strategy witness builders to fix the USDC-only e18 shortcut, redeployed the subgraph at `helios/v0.6.0`, and added `scripts/e2e-scenario.sh phase6-realprice` as the regression harness. Tagged `v0.6.0-realprice`.
- **Passport sign-in three-fix chain (2026-05-09)**: clicking *Sign in with Passport* on the Vercel build surfaced three stacked SDK bugs that masked each other. (1) Particle's bundled pino logger reads `process.stdout.isTTY` during userOp signing — webpack's `ProvidePlugin` resolves `process` to `process/browser`, whose `module.exports = {}` is a separate object from `globalThis.process`, so any polyfill on the global never reached it. Fix: alias `process/browser` → `frontend/process-shim.cjs` in `next.config.mjs`. (2) `ParticleNetwork` resolves the active chain by `chainName.toLowerCase() + "-" + chainId`; `@gokite-network/auth` registers Kite as `gokite-2368`, so passing `chainName: "Kite"` raised EIP-1193 4201 *"The Provider does not support the chain"*. Fix: `chainName: "Gokite"`. (3) `gokite-aa-sdk`'s `NETWORKS` keys are `kite_testnet` / `kite_mainnet` (underscore), but we passed `"kite-testnet"` (hyphen, our internal `ChainKey`). Raised *"Unsupported network: kite-testnet"*. Fix: pass `"kite_testnet"` to the AA SDK constructor. Also surfaced `err.stack` in the onboard "technical detail" toggle so the next failure is diagnosable from DevTools alone.
- **#13 circuit zero-amount reject**: `momentum_v1` and `mean_reversion_v1` accepted `amount_in = 0` at the circuit level — `yield_rotation_v1` had Constraint 7 (`amount_rotating > 0`) but the directional circuits didn't. Fixed via `Num2Bits(128)` on `(amount_in - 1)` mirroring `yield_rotation_v1.circom:209-214`. Severity Medium — no-op trades polluted the attestation stream + reputation calc, but couldn't move capital. **Chain-side closure required a heavy redeploy** (new TAV with PR #70 timelock code + UUPS-upgrade all 9 strategy-vault proxies through a one-shot `migrateVerifier`) because the deployed testnet TAV was the lax pre-PR-#70 version with no in-place rotation path. Both repo + chain landed in a single broadcast; no T+48h commit phase.
- **VPS bring-up bug cluster (2026-05-09)**: first real deploy of the operator stack surfaced six bugs masked by the local docker-compose loop — node base-image UID-1000 collision in `node.Dockerfile`; missing `node` runtime in oracle's python-slim image (Poseidon helper spawns a node subprocess via circomlibjs); `uvicorn.run(callable, reload=True)` silent exit in all three reference-strategy `__main__.py` files (fixed with import-string form); oracle indexed `KITE/USDT`/`ETH/USDT` while strategies queried bare `WKITE`/`WETH` (added aliases); coingecko `kite-ai` slug 404'd post-mainnet relisting (bumped to `kite-2`); strategy oracle client decoded `body["root"]` as hex when oracle returns it as decimal BN254 (now reads `root_bytes32`). All six landed `f263329`…`5d3f50a` and the operator runtime now polls cleanly (`bars_observed: 4`, `last_error: ""`).
- **#17 Reputation V1 `InvalidSigner` revert**: engine posts to V1 anchor and reverts on signer recovery; tracked as follow-up. Not demo-blocking because `/audit` reads the V2 sidecar (`0x735680a3…`).
- **WS9 — autonomous attested-trade bring-up (2026-05-10)**: post user-onboarding the allocator deposits 9 active allocations (Phase-6 capacity-fix redeploy on 2026-05-10) but the strategy services have never fired a `TradeAttested` event — exploration surfaced seven cascading misconfigs blocking `executeWithProof`: (1) oracle 404s on `WBTC/WETH/WSOL` because the live oracle keys snapshots by `BTC/USDT, ETH/USDT, SOL/USDT`; (2) `asset_universe_addresses` never passed from `service.py` Settings to the runtime constructor — falls back to symbols + empty padding; (3) `StrategyRegistry.commitInitialParamsHash` never called for any of the 9 vaults, so `_activeParamsHash() == 0` and every proof reverts `ParamsHashMismatch`; (4) `_DummyBlockProvider` is the default — witness `block_window_start/end` doesn't track the live chain, would revert `WindowExpired`; (5) `ORACLE_ANCHOR_INTERVAL_BARS=50` (commits every 50 minutes) so the strategy's per-bar witness root rarely matches a committed root inside the 180s `MAX_ORACLE_STALENESS_SEC`; (6) operator + NAV PKs (`MOMENTUM_OPERATOR_PK`, `MEAN_REV_OPERATOR_PK`, `YIELD_ROT_OPERATOR_PK`, `NAV_ORACLE_PK`) need to be set to the deployer key on the VPS; (7) only the `.base` variant per class has `*_STRATEGY_VAULT_ADDRESS` wired — 6 of 9 vaults stay idle, deferred. Detailed plan + verification in `/home/emark/.claude/plans/dazzling-spinning-quokka.md`.

## Future work (post-WS9, post-Phase-6 if needed)

- **Wire the other 6 vaults (`variant2`/`variant3` per class)**: each strategy container is hard-wired to one `*_STRATEGY_VAULT_ADDRESS`. To activate the remaining 6 vaults, prefer multi-vault per container — `service.py` reads a `VAULT_ADDRESSES_JSON` list, builds per-vault runtimes, and runs them concurrently (~80 LOC per class, no infra change). Alternative: 9 docker services (simplest but heaviest compose). Demo-acceptable to ship with 3 of 9 firing; long-term the protocol's diversity story wants all 9.
- **Anchor-aligned root fetch in `OracleClient`**: today the strategy computes a root over the latest 16 snapshots and *hopes* the anchor's most recent commit covers the same window. With cadence=1 these align ≥95% of the time but a one-bar race can still cause `UnknownOracleRoot` reverts ~5% of bars. Hardening: add a `GET /v1/snapshots/at?asset=X&windowEnd=T` endpoint, change `OracleClient.fetch_recent` to anchor-then-fetch (read `OraclePriceAnchor.commitAt(commitCount()-1)` then ask oracle for the matching snapshot window). ≤200 LOC, zero contract changes. Phase-7 hardening item.

## Demo deadline

**2026-05-18** (9 days from today). Real-price stack is live; remaining critical path is WS5-prep user actions → first attested trade → demo materials → cold-judge dry run → `v1.0.0`.
