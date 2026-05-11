# Dead/unneeded code cleanup

## Context

The Helios tree has accumulated Phase-1/2 scaffolding, a fully scope-cut Telegram bot, deferred-to-v2 SDK helpers, and a leftover scratch circuit. With Phase 6 in flight and `v0.5.0` about to ship, the goal is to delete code that no longer earns its place while keeping anything that still gates a test, a published SDK, or the active e2e harness. User direction: **aggressive — delete scope-cut + deferred; delete superseded deploy scripts; prune broadcasts for deleted scripts.**

Three findings groups; one **needs reconfirmation** because of public-SDK implications.

---

## Group A — Safe deletes (high confidence, no coupling)

### A1. Scratch circuit artifacts
- `circuits/build/hello/` (entire directory; ~5 MB of `.r1cs`/`.wasm`/`.zkey`/`.sym`)
- Any `hello` target left in `circuits/Makefile` (verify on edit)

Evidence: no references in contracts, scripts, services, or tests. Built 2026-04-26, untouched since.

### A2. Deprecated Phase-3 base-trio smoke
- `scripts/e2e_base_trio_smoke.py` (docstring: *"DEPRECATED — historical Phase-3 smoke check. Will fail post-cutover"*)
- `scripts/e2e-base-trio-smoke.sh` (only caller)

Evidence: base-trio carve-out retired per memory `project_phase3_deploy_state.md`; no CI wiring.

---

## Group B — Phase-1/2 lineage (coupled — delete as one unit)

The Phase-1/2 deploy scripts cannot be deleted in isolation: they have Foundry tests, a dedicated e2e harness, and the default branch of `scripts/e2e-scenario.sh` (Track A) invokes `DeployPhase1`. Delete the lineage as a single change.

### B1. Foundry scripts (`contracts/script/`)
- `DeployPhase1.s.sol`
- `DeployPhase2.s.sol`
- `DeployPhase3.s.sol` (never broadcast; placeholder for refreshed-testnet path that never landed)
- `RegisterPhase2Strategies.s.sol`
- `RegisterPhase2StrategiesVariant3.s.sol`

### B2. Foundry tests (`contracts/test/`) — drop tests that target removed scripts
- `DeployPhase1.t.sol` (if present)
- `DeployPhase2.t.sol`
- `DeployPhase3.t.sol`
- `RegisterPhase2Strategies.t.sol` (line 8 imports the script directly — fails to compile once script is gone)

### B3. Phase-1/2 e2e harness (Python + shell)
- `scripts/e2e_scenario_phase2.py`
- `scripts/e2e-scenario-phase2.sh`
- `scripts/_phase2_oracle_nav.py`
- `scripts/_phase2_witness.py`
- `scripts/_phase2_reputation_local.py`
- `scripts/e2e_scenario.py` (Phase-1 driver — only caller of `_phase2_oracle_nav._commits_for_anchor`)
- `scripts/e2e-phase3.sh` (no-op stub waiting on `DeployPhase3`)
- `scripts/verify_phase2_anchors.py`
- `scenarios/_generate_phase2.py`
- `scenarios/phase2-multi-class.json`

### B4. Default-mode rewrite of `scripts/e2e-scenario.sh`
Drop Track A entirely. Keep the `phase5` and `phase6-realprice` modes (these are the live harnesses). The script's header comment + arg-parser need pruning; if no callable modes remain, delete the script.

### B5. Stale broadcast directories (only after B1 lands)
- `contracts/broadcast/DeployPhase1.s.sol/`
- `contracts/broadcast/DeployPhase2.s.sol/`
- `contracts/broadcast/RegisterPhase2Strategies.s.sol/`
- `contracts/broadcast/RegisterPhase2StrategiesVariant3.s.sol/`

### B6. Docs/TODO sweep
- `TODO.md`: scrub Phase-1/2 historical bullets that reference the removed scripts (or just mark the affected sections as "see git history").
- `.env.example` line 117 (`SCENARIO_FILE=scenarios/phase1-drawdown.json`) — keep `phase1-drawdown.json` itself; oracle service + tests still reference it (`services/oracle/tests/test_service.py`, `services/oracle/sources/scenario.py`, `services/_template/src/_template/config.py`).

### B7. Notes on B
- `scenarios/phase1-drawdown.json` **stays** — oracle scenario-mode tests still consume it.
- `RedeployBaseTrioStrategyVaults.s.sol`, `RedeployBaseVaultsWithOperators.s.sol` — verify on touch; these may be one-shots too, but they're more recent and may still be replay-needed. Default to **keep**.

---

## Group C — Scope-cut Telegram bot

Scope-cut per `project_phase3_scope_cuts.md`; no production importer.

- `services/bot/` (entire directory)
- `pyproject.toml`: remove from `[tool.uv.workspace] members` line 36 and `[tool.uv.sources]` line 52
- `CLAUDE.md`: drop the `services/bot/` row from the repo map (line 37); drop the `TELEGRAM_BOT_TOKEN` row (line 92)
- `deploy/README.md`: drop lines 97 + 148 references
- `TODO.md`: lines 46, 563 — drop bullets or trim the "Deferred" section explanation
- `.env.example`: drop `TELEGRAM_BOT_TOKEN` entry if present

---

## Group D — Skipped (kept by decision)

The deferred helpers below are public exports of `helios-allocator-sdk` (published to PyPI). Decision: **keep them.** Zero runtime cost in v1, documented v2 extension point, and removing them would be a SemVer break on a public SDK. Reference list retained below for traceability only — **no action**.

## Group D (reference only — not executing)

The "deferred v2" helpers flagged in exploration are **exported public API** of `helios-allocator-sdk`, which is published to PyPI (and test-PyPI per memory `project_testpypi_oidc_setup.md`) for third-party allocators to build against. Removing them is a SemVer-breaking change to a shipped package. There's also a guard test that asserts the v1 Helix allocator *does not* call them.

Affected files if we proceed:
- `packages/allocator-sdk/src/helios_allocator/helpers/correlation.py` (`helix_greedy_pick`, `pairwise_correlation_from_goldsky`)
- `packages/allocator-sdk/src/helios_allocator/helpers/regime.py` (`detect_regime` — but **keep** `helix_fee_factor` if still imported elsewhere; verify)
- `packages/allocator-sdk/src/helios_allocator/helpers/market_data.py` (`btc_realized_vol_30d`, `btc_vol_percentiles_1y`, `OracleHTTPReader`, `StaticMarketData`, `MarketDataReader`)
- `packages/allocator-sdk/src/helios_allocator/helpers/__init__.py` — drop the exports + `__all__` entries
- `packages/allocator-sdk/tests/test_helpers_correlation.py`, `test_helpers_regime.py`, `test_helpers_market_data.py` — drop tests for removed symbols
- `services/helix/tests/test_allocator.py:169-180` — `test_does_not_call_helix_greedy_pick_in_v1` asserts the symbol exists; either delete the test or invert it
- `services/helix/src/helix/allocator.py` — drop the doc-comment references (lines 16, 21)

**Implication:** next allocator-sdk wheel needs a major-version bump and a CHANGELOG note. Third-party allocators built against the current API would fail to import after upgrading.

**Recommendation:** keep Group D unless you want to break SDK compat. They're well-tested dead-on-arrival surface, but they're also the documented extension points for v2-class allocators (CLAUDE.md repo map flags `allocator-sdk` as the **public** SDK).

---

## Critical files to touch

| Path | Group | Action |
|---|---|---|
| `circuits/build/hello/` | A1 | rm -rf |
| `circuits/Makefile` | A1 | edit (if `hello` target exists) |
| `scripts/e2e_base_trio_smoke.py`, `scripts/e2e-base-trio-smoke.sh` | A2 | delete |
| `contracts/script/Deploy{Phase1,Phase2,Phase3}.s.sol` | B1 | delete |
| `contracts/script/RegisterPhase2Strategies{,Variant3}.s.sol` | B1 | delete |
| `contracts/test/{DeployPhase2,DeployPhase3,RegisterPhase2Strategies}.t.sol` | B2 | delete |
| `scripts/_phase2_*.py`, `scripts/e2e_scenario{,_phase2}.py`, `scripts/verify_phase2_anchors.py`, `scripts/e2e-scenario-phase2.sh`, `scripts/e2e-phase3.sh` | B3 | delete |
| `scenarios/_generate_phase2.py`, `scenarios/phase2-multi-class.json` | B3 | delete |
| `scripts/e2e-scenario.sh` | B4 | rewrite or delete |
| `contracts/broadcast/{DeployPhase1,DeployPhase2,RegisterPhase2*}/` | B5 | rm -rf |
| `TODO.md`, `CLAUDE.md`, `deploy/README.md`, `.env.example` | B6 / C | docs sweep |
| `services/bot/` | C | rm -rf |
| `pyproject.toml` | C | drop workspace + sources entries |
| `packages/allocator-sdk/src/helios_allocator/helpers/*` + tests | D | **skipped — keep** |

---

## Verification

After each group lands, run independently — each group is a separate PR-sized commit so any failure is isolated.

**Group A**
- `cd circuits && make momentum_v1 && make mean_reversion_v1 && make yield_rotation_v1` — circuits still build.
- `grep -rn "e2e_base_trio_smoke\|hello\.r1cs" --exclude-dir=node_modules` — no hits.

**Group B**
- `cd contracts && forge build && forge test -vv` — passes (key check: `RegisterPhase2StrategiesTest` is gone, nothing else references the deleted scripts).
- `uv run pytest services/oracle services/sentinel` — passes (oracle scenario-mode still finds `phase1-drawdown.json`).
- `bash scripts/e2e-scenario.sh phase6-realprice` — the live e2e mode still runs.
- `grep -rn "DeployPhase1\|DeployPhase2\|RegisterPhase2Strategies\|_phase2_\|phase2-multi-class\.json" --exclude-dir=node_modules --exclude=*.md` — empty (markdown allowed: historical bullets in TODO.md).

**Group C**
- `uv sync` — pyproject parses with `services/bot` removed.
- `uv run pytest services/sentinel services/oracle services/reputation services/helix` — no bot imports break anything.
- `grep -rn "services/bot\|TELEGRAM_BOT_TOKEN" --exclude-dir=node_modules --exclude=*.md` — empty.

**Group D** — skipped.
