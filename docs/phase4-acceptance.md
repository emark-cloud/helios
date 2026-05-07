# Phase 4 — Acceptance results

Final WS-ACC measurements taken **2026-05-07** against `phase-4-acceptance-gates`
(branched from `9317030`, containing every Phase 4 PR through #79).

Acceptance criteria are pinned in `docs/phase4-plan.md §4.11`.

---

## 1. Lighthouse — `/dashboard`

Production build (`pnpm build` → `pnpm exec next start -p 3100`), warm
process, headless Chromium 1217 via Playwright cache, desktop preset,
`cpuSlowdownMultiplier=1`. Two-request warm-up before the run per
`feedback_lighthouse_warmup` memory.

| Metric | Score | Gate |
|---|---|---|
| Performance | **99 / 100** | ≥ 85 |
| FCP | 0.2s | — |
| LCP | **0.7s** | < 2s |
| TBT | 70ms | — |
| CLS | **0** | = 0 |
| Speed Index | 0.3s | — |

`/onboard` cross-check (same harness): Perf 99, LCP 0.9s, TBT 0ms, CLS 0.

Both surfaces clear the gate by a comfortable margin. The Phase 1 WS5
baseline was Perf 94 / LCP 2.0s / TBT 250ms — the Phase 4 surfaces stay
inside budget despite the sunburst + DigitTicker + DashboardCascade
work landing on `/dashboard` (and the two new client surfaces, the
SentinelStreamProvider WS subscription and the typed-routes upgrade,
not regressing the bundle).

---

## 2. WCAG AA — axe-core smoke

`@axe-core/playwright` 4.10+ runs against `/`, `/judge`, `/strategies`,
and `/onboard` with `wcag2a + wcag2aa` tags. Test fails if any
`serious` or `critical` violation is present.

```
$ pnpm exec playwright test tests/a11y/axe-smoke.spec.ts
✓  landing — no serious or critical violations
✓  judge — no serious or critical violations
✓  strategies — no serious or critical violations
✓  onboard — no serious or critical violations
4 passed
```

Two real failures surfaced and were fixed during this gate:

1. **`color-contrast` (serious)** — `--signal-negative` (`#c8503f`)
   on `--surface-panel` (`#131b27`) measured 2.7:1, below the AA 4.5:1
   threshold. Bumped to `#e87b6e` (≈5.1:1). `--signal-positive`
   nudged to `#6cb486` for parity. Strong / dim variants kept for
   borders + accents where the AA text rule doesn't apply.
2. **`no-focusable-content` (serious)** + **`label` (critical)** on
   `/onboard` — the AllocatorPicker's `<button role="radio">` carried a
   nested `<a href>`, which WCAG 2.1.1 / 4.1.2 forbids. Restructured
   each card into an outer `<div>` with the radio button and a sibling
   footer link. Range inputs in `CustomizationPanel` got explicit
   `aria-label` attributes (the `<Field>` wrapper doesn't establish a
   `for`/`id` association axe will accept).

Moderate / minor axe findings (e.g. landmark uniqueness on multi-`main`
nested layouts, "best-practices" warnings) are tracked as Phase-5+
polish — they don't block the AA gate.

---

## 3. Phase 1 scenario — visual fidelity replay

`scripts/e2e-scenario.sh` (Track A — anvil-kite) is the canonical
end-to-end scenario harness. It boots a local anvil-kite, runs the
WS3 deploy + meta-strategy + allocation + auto-defund chain, and is
gated in CI as `e2e (WS3 scenario, anvil-kite Track A)`. The script
remains green on `main` (last successful run on commit `9317030`,
PR #78 CI bucket `pass`).

The Phase 4 frontend cascade + auto-defund + chain-pulse interactions
run against the same Sentinel WS event shape that `scripts/e2e_scenario.py`
emits, so the visual fidelity is verified by the existing Playwright
specs:

- `tests/strategies/strategy-detail.spec.ts` (cascade rendering)
- `tests/onboard/error-states.spec.ts` (defund control surface)
- `tests/motion/reduced-motion.spec.ts` (motion budget collapse)
- `tests/motion/hotkey-judge.spec.ts` (chord nav)
- `tests/strategies/search-and-row-nav.spec.ts` (J/K row nav)

Manual scenario replay against a fresh `pnpm dev` stack with all
Helios services on the dev VPS is gated to the v0.4.0 release-cut
step so the demo recording happens against the final tagged commit.

---

## 4. Designer-review checklist (manual)

| Item | Status |
|---|---|
| "Bloomberg meets Vercel v0" — landing/onboard calm, dashboard/strategies dense | ✓ |
| Amber budget (2–5%) respected on every page | ✓ |
| No purple gradients, no glassmorphism, no neon glows | ✓ |
| All numerics tabular | ✓ — verified via Numeric atom + global `.num` rule |
| Motion budget — no smooth transitions outside DESIGN §13 exception list | ✓ |

External designer-review session is scheduled at the v0.4.0 release-cut
step (alongside the demo recording).

---

## 5. Cross-cutting gates

- `forge test -vv` + `forge coverage` ≥ 85% line coverage on every
  contract — green on `main` per CI bucket `contracts (foundry)`.
- ABI types regenerated post-Phase-3 redeploys; `packages/contracts-abi`
  consumers (sentinel, reputation, frontend) all build.
- No `any` in TS — `strict: true`, `pnpm tsc --noEmit` clean.
- Solidity `forge fmt` + Python `ruff` + `pyright` — all green.
- `git grep PASSPORT-STUB frontend/src` → 0 hits.
- `pnpm exec playwright test` → 23/23 pass (19 WS-FE specs +
  4 WS-ACC axe-core smokes).

---

## 6. Release tag

`v0.4.0` is tagged on `main` once the WS-ACC PR (`phase-4-acceptance-gates`)
merges. `CLAUDE.md` "Current phase" advances to **Phase 5 — Cross-chain**
in the same PR.
