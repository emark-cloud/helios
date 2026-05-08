# Phase 6 — Polish + submission plan

> **Source of truth:** `TODO.md` Phase 6 block; `DESIGN.md §9.7-§9.8, §13`; `Helios.md §15, §19`.

## Context

Phases 0–5 complete as of 2026-05-08. `v0.5.0` lands once the WS8 acceptance PR merges. Phase 6 is judge-readiness + defensibility under scrutiny on the testnet stack. Mainnet promotion stays in the Stretch section (`TODO.md` line 506) — exercised only if time remains.

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
- **WS5-prep** — trigger ≥ 1 attested trade on Kite testnet. The 2026-05-08 StrategyVault redeploys created fresh addresses with no traffic; `verify-trade.js` has no PASS smoke target until a real `executeWithProof` lands.
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

## Status snapshot (2026-05-08, mid-day)

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
| #13 — Circuit zero-amount reject (mom + MR) | 🟡 repo-side **complete**: circuits edited, artifacts regenerated (.r1cs/.wasm/.zkey/Solidity verifier), tests added (43/43 circuit + 390/391 forge + 10/10 prover pass), docs updated. Chain-side **pending broadcast**: `ProposeVerifierRotation.s.sol` + `CommitVerifierRotation.s.sol` written; runbook at `docs/phase6-circuit-rotation-runbook.md`. Awaiting deployer-key broadcast (Step 1). Commit at T0 + 48h. |
| WS5-prep — testnet attested trade | ⏳ blocked on user (needs operator/oracle keys + KITE for gas) |
| WS5 — Demo materials | ⏳ blocked on WS5-prep |
| WS6 — Acceptance + tag | ⏳ gated on all above |

## Newly-uncovered work (during Phase 6)

- **#13 circuit zero-amount reject**: `momentum_v1` and `mean_reversion_v1` accept `amount_in = 0` at the circuit level — `yield_rotation_v1` has Constraint 7 (`amount_rotating > 0`) but the directional circuits don't have an analogue. Fix: `Num2Bits(128)` on `(amount_in - 1)` mirroring `yield_rotation_v1.circom:209-214`. Severity Medium — no-op trades pollute attestation stream + reputation calc, can't move capital. **TAV `CHANGE_DELAY = 2 days`** on `verifierByClassMap` rotation — propose today, commit T+48h.

## Demo deadline

**2026-05-18** (10 days from today). Comfortable runway for the 48h TAV timelock on #13.
