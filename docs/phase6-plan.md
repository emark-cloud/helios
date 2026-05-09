# Phase 6 — Polish + submission plan

> **Source of truth:** `TODO.md` Phase 6 block; `DESIGN.md §9.7-§9.8, §13`; `Helios.md §15, §19`.

## Context

Phases 0–5 complete as of 2026-05-08; `v0.5.0` tagged on `main`. Phase 6 is judge-readiness + defensibility under scrutiny on the testnet stack. Mainnet promotion stays in the Stretch section (`TODO.md` line 506) — exercised only if time remains.

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

### WS5 — Demo (depends on WS5-prep)
- **WS5-prep** — trigger ≥ 1 attested trade on Kite testnet. The 2026-05-08 StrategyVault redeploys created fresh addresses with no traffic; `verify-trade.js` has no PASS smoke target until a real `executeWithProof` lands. **Operator runtime stood up 2026-05-09** (VPS compose stack + Vercel frontend + Passport credentials wired); now blocked only on user-side actions (KITE faucet, mUSDC mint, `/onboard` deposit + delegate).
- 3-minute live demo script (markdown checklist in `docs/demo-runbook.md`).
- 90-second backup video + hosted URL linked from `/judge` and README.
- Cold-start verification: fresh-clone → `pnpm install && uv sync && forge install && pnpm dev` → `scripts/e2e-scenario.sh` finishes within 10 minutes. Document the timing.

### WS6 — Phase 6 acceptance + tag (gated on everything)
- Cold-judge dry run: 5-step `/judge` checklist completes in under 5 minutes, including independent ZK verify.
- Slither/Mythril clean (or every finding documented).
- Cut `v0.5.0` once the WS8 acceptance PR merges; cut `v1.0.0` once Phase 6 acceptance passes.

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

## Status snapshot (2026-05-09)

| Track | Status |
|---|---|
| WS1.A — verify-trade.js | ✅ written; PASS smoke pending WS5-prep |
| WS1.B — /judge + /audit audit | ✅ punch list returned |
| WS1.B-followups | ✅ all FE blockers fixed; typecheck + lint clean |
| WS2.A — Slither CI + audit-checklist | ✅ workflow + 9H/27M/57L/227I triage doc; all 9H are known false positives in snarkjs-generated verifiers |
| WS2.B — threat-model doc | ✅ 14 rows, 10 mitigated / 4 accepted |
| WS3 — Deploy hardening | ✅ Nginx tuned to spec (100/min reads, 10/min writes, 5/min prover); postgres-backup.sh + restore runbook; deploy/README.md expanded; secrets audit clean |
| WS4 — Docs (allocator, circuit-specs, README) | ✅ allocator-guide 631L; circuit-specs 555L; README rewritten |
| #11 — Circuit test coverage gaps | ✅ 7 new tests; 58/58 passing |
| #12 — Allocator-init scaffold fix | ✅ template rewritten; verified end-to-end with real install + boot |
| #13 — Circuit zero-amount reject (mom + MR) | ✅ **fully closed (repo + chain) 2026-05-08**. Circuits add Constraint 0 (`Num2Bits(128)` on `amount_in - 1`); artifacts regenerated (43/43 circuit + 394/395 forge + 10/10 prover); new TAV `0x3698F60a…` deployed with PR #70 timelock code (the legacy testnet TAV at `0x743e1bd7…` was the lax pre-PR-#70 version with no rotation path, so a heavy redeploy + UUPS upgrade was the only viable path); new mom + MR verifier+adapters; new `StrategyVault` impl `0x934f7639…` adds `migrateVerifier(reinitializer(2))`; all 9 vault proxies upgrade-and-call'd to the new TAV in one tx each. JSON + CLAUDE.md updated. |
| WS5-prep — VPS operator runtime | ✅ first-time VPS deploy 2026-05-09 — postgres, redis, prover, sentinel, reputation, oracle, momentum_v1 all up under compose; oracle anchoring real prices on-chain (yield + price txs landed); 6 production bugs fixed in flight (`f263329` uvicorn reload, `b62eb53` WKITE/WETH alias, `8e91207` coingecko `kite-2` slug, `c363a51` `root_bytes32` decode, node-Dockerfile UID collision, oracle Poseidon node install). |
| WS5-prep — frontend on Vercel | ✅ live at `helios-frontend-steel.vercel.app`; Particle Passport credentials wired (project / client / app id); pino-logger `isTTY` polyfill landed (`942dd24` → typed shim `1850730`). |
| WS5-prep — testnet attested trade | ⏳ blocked on user-side: KITE faucet drip + mUSDC mint to Passport AA address + click `/onboard` to deposit + delegate. |
| WS5 — Demo materials | ⏳ blocked on first attested-trade tx hash. |
| WS6 — Acceptance + tag | ⏳ gated on WS5; will cut `v1.0.0` once cold-judge dry run passes. |
| #17 — Reputation V1 `InvalidSigner` revert | ⏳ tracked; not demo-blocking — V2 sidecar is what `/audit` reads. |
| #18 — VPS pm2 systemd unit + nginx swap | ⏳ deferred; needs sudo password from user. |

## Newly-uncovered work (during Phase 6)

- **#13 circuit zero-amount reject**: `momentum_v1` and `mean_reversion_v1` accepted `amount_in = 0` at the circuit level — `yield_rotation_v1` had Constraint 7 (`amount_rotating > 0`) but the directional circuits didn't. Fixed via `Num2Bits(128)` on `(amount_in - 1)` mirroring `yield_rotation_v1.circom:209-214`. Severity Medium — no-op trades polluted the attestation stream + reputation calc, but couldn't move capital. **Chain-side closure required a heavy redeploy** (new TAV with PR #70 timelock code + UUPS-upgrade all 9 strategy-vault proxies through a one-shot `migrateVerifier`) because the deployed testnet TAV was the lax pre-PR-#70 version with no in-place rotation path. Both repo + chain landed in a single broadcast; no T+48h commit phase.
- **VPS bring-up bug cluster (2026-05-09)**: first real deploy of the operator stack surfaced six bugs masked by the local docker-compose loop — node base-image UID-1000 collision in `node.Dockerfile`; missing `node` runtime in oracle's python-slim image (Poseidon helper spawns a node subprocess via circomlibjs); `uvicorn.run(callable, reload=True)` silent exit in all three reference-strategy `__main__.py` files (fixed with import-string form); oracle indexed `KITE/USDT`/`ETH/USDT` while strategies queried bare `WKITE`/`WETH` (added aliases); coingecko `kite-ai` slug 404'd post-mainnet relisting (bumped to `kite-2`); strategy oracle client decoded `body["root"]` as hex when oracle returns it as decimal BN254 (now reads `root_bytes32`). All six landed `f263329`…`5d3f50a` and the operator runtime now polls cleanly (`bars_observed: 4`, `last_error: ""`).
- **#17 Reputation V1 `InvalidSigner` revert**: engine posts to V1 anchor and reverts on signer recovery; tracked as follow-up. Not demo-blocking because `/audit` reads the V2 sidecar (`0x735680a3…`).

## Demo deadline

**2026-05-18** (9 days from today).
