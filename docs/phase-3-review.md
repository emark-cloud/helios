# Phase 3 Codebase Review — Consolidated Punch List

Six parallel reviews ran across contracts, circuits, services, SDKs/CLI, frontend, and peripheral surfaces. Below is the de-duped roll-up, ordered by severity. Per-surface findings (with file:line for every item) are summarized inline; raw agent outputs were captured in the conversation that produced this document.

Date: 2026-05-06
Scope: post-Phase 3, pre-Phase 4

---

## CRITICAL — fix before any new feature work

1. **Allocator-SDK meta-strategy signature has no nonce/deadline** — `packages/allocator-sdk/src/helios_allocator/service/auth.py:50`. Indefinite replay across allocators; can re-bind a delegation the user already revoked off-chain.
2. **Oracle anchor nonce desync after dry-run → live** — `services/oracle/src/oracle/anchor.py:288–334`. Off-chain `_nonce` is not realigned to on-chain `_read_onchain_nonce`, emits stale-nonce commits on resume.

---

## HIGH — spec violations or capital-at-risk bugs

### Contracts

3. `AllocatorVault.defundStrategy` is missing the entire §6.3 anti-grief mechanism (TWAP bars, bond, confirm window) — currently a single-point NAV check, exactly the front-run surface the spec calls out. (`contracts/src/AllocatorVault.sol:170-197`)
4. `AllocatorVault.settleStrategyFee` is permissionless **and** the HWM update is `+= realized` instead of `= max(hwm, navAtSettlement)`, allowing fee double-charging on NAV oscillation. (`AllocatorVault.sol:230-280`)
5. `UserVault.setMetaStrategy` has no auth around tightening fields while capital is allocated; can grief an active position into permanent-revert state. (`UserVault.sol:104-149`)
6. `StrategyVault.executeWithProof` doesn't enforce oracle freshness (`MAX_STALENESS_SEC = 180s`); only checks root membership. (`StrategyVault.sol:312-353`)
7. `StrategyVault.reportNAV` has no replay window, no caller restriction, and no NAV-divergence slashing as required by §6.4. (`StrategyVault.sol:523-542`)
8. `StrategyVault.withdrawToAllocator` lets one allocator drain past its NAV share when `amount > _totalNAV`. (`StrategyVault.sol:235-256`)
9. `OraclePriceAnchor.revokeRoot` is irreversible, and there is no `freshness()` view — a misclick permanently bricks every trade referencing that root. (`OraclePriceAnchor.sol:62-67,77-107`)
10. No global pause / circuit breaker on UserVault, AllocatorVault, StrategyVault. UUPS owner is single-key.

### Circuits

11. Momentum `is_signal_flip` only models long→down reversals; short positions cannot ever exit via flip (completeness bug). (`circuits/momentum_v1.circom:213-218`)
12. Momentum + mean-reversion don't constrain `asset_in_idx ≠ asset_out_idx` (yield-rotation does); self-swap proofs verify. (`momentum_v1.circom:113-122`, `mean_reversion_v1.circom:98-109`)
13. Momentum + MR slippage check has unconstrained widths on `amount_in` / `min_amount_out` — a near-field-size value wraps and `LessEqThan(160)` still passes. Add `Num2Bits(128)` range checks. (`momentum_v1.circom:135`, `mean_reversion_v1.circom:121`)

### Services

14. Allocator runtime drawdown check uses single-point NAV vs HWM (`packages/allocator-sdk/src/helios_allocator/runtime/loop.py:163`), same flash-crash-defund problem as the contract layer; needs TWAP read off `OraclePriceAnchor`.
15. Reputation engine and oracle anchor have unbounded `pending` lists — long-running services OOM. Cap to ring buffers. (`services/reputation/src/reputation/anchor.py:55,96`; `services/oracle/src/oracle/anchor.py:149`)
16. AllocatorStore `_events` grows without bound globally even though `recent_events` filters by user. (`packages/allocator-sdk/src/helios_allocator/runtime/state.py:100,140`)
17. Prover service: no auth, no rate limit, no CORS on a public 3–5s-CPU endpoint; `withTimeout` rejects but lets snarkjs keep spinning, exhausting workers. (`services/prover/src/index.js:48,80`)
18. Sentinel + Helix `/v1/users/{user}/events` WebSockets have no auth — anyone can subscribe to any user's allocations + balances. (`services/sentinel/src/sentinel/service.py:189`, `services/helix/src/helix/service.py:192`)
19. Reputation `/v1/audit/{actor}` only reads the strategy dict, never `latest_allocators` — every allocator audit 404s after WS5.A. (`services/reputation/src/reputation/service.py:181,193`)

### SDK / CLI

20. All three reference strategies report `available_capital` (free cash) as `totalNAV` instead of `nav` — under-reports NAV by the entire deployed amount. (`reference-strategies/{momentum_v1,mean_reversion_v1,yield_rotation_v1}/src/.../runtime.py:~260-274`)
21. Reference-strategy wheels declare `helios-service-template` as a runtime dep, but that package is not in the test-PyPI matrix — wheels are uninstallable from PyPI. (`reference-strategies/*/pyproject.toml:7`)
22. `helios-cli/allocator.py:618,625` `deploy()` skips the SSH target validator that `strategy.py` uses; `-oProxyCommand=` injection possible.

### Deploy

23. `deploy/nginx/helios.conf` is HTTP-only (port 80, no TLS, no redirect). Dashboard, prover, oracle, reputation traffic plaintext.

---

## MEDIUM — should fix before Phase 4

### Contracts

- `AllocatorVault.rebalance` ignores `meta.rebalanceCadenceSec`; can rebalance every block.
- `AllocatorVault` permanently blocks re-allocation to a once-defunded `(user, strategy)` pair — clear `defundedAt = 0` when `capitalDeployed = 0`.
- Multi-allocator share dilution in `StrategyVault.distributeRealized`: decrementing `_totalNAV` by a single allocator's above-principal share silently dilutes the others. (`StrategyVault.sol:259-270`)
- `TradeAttestationVerifier.registerVerifier` overwrites without timelock; spec implies "binding circuit ↔ verifier" should be once-set or multi-sig-timelocked.
- `AllocatorRegistry._nameKey` only ASCII-lowercases — trailing space and zero-width-space brand-impersonation paths are open. (`AllocatorRegistry.sol:251-263`)
- All UUPS contracts: `_authorizeUpgrade` is single-owner (no timelock / multisig).
- `StrategyRegistry.deactivate` has no active-allocation check — operator can freeze allocators with capital still deployed.
- `ReputationAnchor` lacks a pause/emergency-halt; signer rotation does not invalidate already-signed-but-unposted updates.

### Circuits

- Yield-rotation circuit comment still says "12 signals" (it's 13 since `block_window_start` was added). (`yield_rotation_v1.circom:11`)
- Window deltas not range-checked (`end < start` produces confusing prover errors rather than a clean revert).

### Services

- Reputation `_max_drawdown_bps` and Sharpe assume sorted snapshots; cache merge preserves order today but no defensive `sorted()` makes a future event-source change a silent bug. (`services/reputation/src/reputation/engine.py:481-500`; `score.py:223`)
- Reputation engine has no submit lock around `_read_onchain_nonce` + `post` — concurrent strategy + allocator ticks can race on the same nonce. (`anchor.py:158`)
- Binance source uses `time.time()` instead of kline `closeTime`, drifting bar timestamps up to 60s. (`services/oracle/src/oracle/sources/binance.py:52`)
- CoinGecko `_float_to_e18` raises on scientific-notation values (`1e-05`). (`services/oracle/src/oracle/sources/coingecko.py:62`)
- Sentinel + Helix `/v1/strategies` directory returns hardcoded `realized_volatility_30d=0`, `sharpe_30d=0`, `max_drawdown_30d_bps=0` — placeholder fields should be populated or dropped. (`sentinel/service.py:262-265`)
- `_template/src/_template/app.py:51-57` — CORS `allow_methods=["*"]`, `allow_headers=["*"]` with `allow_credentials=True` is dangerously permissive for a template.

### SDK / CLI

- Allocator-SDK backtest runner doesn't assert `Σ targets ≤ user_capital` — a buggy ranker silently shows leveraged P&L. (`packages/allocator-sdk/src/helios_allocator/backtest/runner.py:160-166`)
- Yield-rotation strategy emits a phantom rotation on first tick (no active market yet). (`reference-strategies/yield_rotation_v1/src/yield_rotation_v1/strategy.py:96-102`)
- Strategy-SDK backtest VWAP averaging only handles LONG side. (`packages/strategy-sdk/src/helios/backtest.py:380-400`)
- `RotationIntent.amount_in_usd` is `float`, then converted via `int(... * 10**18)` — precision loss above ~9.0e6 USD. (`packages/strategy-sdk/src/helios/types.py:142-153`)

### Frontend

- `ActivityRail` key collision (`${timestamp}-${i}`) re-mounts old rows on every new event — broken animations + perf cost. (`frontend/src/components/dashboard/ActivityRail.tsx:61`)
- `AllocatorLeaderboard.pickTopRows` produces sparse arrays then `.filter(Boolean)` silently reorders pinned rows. (`AllocatorLeaderboard.tsx:65-71`)
- `sentinel.ts.subscribeUserEvents` has no reconnect; ActivityRail stays "Disconnected" until address change. (`frontend/src/lib/sentinel.ts:185-209`)
- `AllocatorPicker.tsx:130` uses `as never` — bypasses typed routes.
- DESIGN.md token system bypass: `accent-[var(--accent-amber)]` raw CSS-var instead of a Tailwind token. (`CustomizationPanel.tsx:141,183,289`)

### Subgraph / CI / Deploy

- `Allocation.capitalDeployed` writes `delta` in three handlers and `amount` in one — inconsistent semantics. Either rename or normalize. (`subgraph/src/allocator-vault.ts:116,140`)
- `DefundEvent.capitalRecovered = a.capitalDeployed` reads the per-event scalar (wrong by design). (`subgraph/src/allocator-vault.ts:173`)
- `prover` service has no `healthcheck` in `docker-compose.prod.yml` — hung snarkjs not detected. (`deploy/docker-compose.prod.yml:49-65`)
- Python Dockerfile is single-stage (~600MB+); needs multistage. (`deploy/services/python.Dockerfile`)
- CI has no `cache: pnpm` / `enable-cache: true` for uv — every PR re-resolves. (`.github/workflows/ci.yml`)
- CI artifact uploads `/tmp/helios-e2e-deploy.log` on failure — tripwire once a real `DEPLOYER_PK` lands as a secret. (`.github/workflows/ci.yml:225-233`)

---

## LOW — cleanup / hygiene

### Dead code

- `frontend/src/components/icon/index.tsx:81-90` `FlowIcon` is exported but never imported.
- `frontend/src/lib/sentinel.ts:138-143` legacy `postMetaStrategy` (only `postMetaStrategyTo` is used).
- `frontend/src/components/dashboard/WithdrawControl.tsx:14-35` Phase-2 stub still disabled despite UserVault being deployed.
- `frontend/src/components/allocators/AllocatorCard.tsx:23,121` `HELIX_FEE_BPS_THRESHOLD = 0` is functionally unused.
- `frontend/src/app/page.tsx` Phase-0 token swatch landing still ships at `/`.
- `packages/helios-cli/src/helios_cli/allocator.py:406` web3 v6 `rawTransaction` fallback (pyproject pins ≥7.4).
- `packages/helios-cli/src/helios_cli/_chain.py:58` plaintext PK field — derive `LocalAccount` immediately.

### Hygiene

- CLAUDE.md says `pnpm dev` boots "all services + frontend"; reality is just compose + frontend. Doc drift.
- No `helios scaffold-strategy` smoke target in `package.json` (project memory: judging-audit visibility gap).
- Verifier adapters use `for (i=0; i<14; i++) fixedInputs[i] = publicInputs[i]` — wasteful (~3k gas × every trade); `calldatacopy` instead.
- `deploy/bootstrap.sh:65-67` adds `helios` user to `sudo` group AND grants NOPASSWD nginx — sudo membership is unnecessary.
- Many `pending` arrays / event caches in services never evict by strategy deactivation (memory growth, not a leak).
- `circuits/yield_rotation_v1.circom:11` doc-comment stale (says 12 PI, now 13).
- `OraclePriceAnchor.setSigner` has no two-step / time-locked rotation.
- `StrategyVault.slash` halts the vault but does not pull stake (financial slash routes through registry); dual-purpose `slash` is confusing — split or document.
- `frontend/src/lib/format.ts:63-66` `formatAddress` doesn't checksum — unchecksummed addresses display in audit/judging UI.
- `frontend/src/lib/wagmi.ts:8` falls back to `""` `projectId`; WC connector silently disables in misconfigured prod.

---

## Suggested fix order (highest leverage first)

1. **Contracts §6.3 anti-grief** + **oracle freshness** + **`reportNAV` replay window** — the three together are the load-bearing safety story; no Phase 4 should ship without them.
2. **Capital math**: `settleStrategyFee` HWM, `withdrawToAllocator` NAV cap, multi-allocator dilution in `distributeRealized`. Land alongside #1.
3. **Allocator-SDK signature nonce + WS auth** — meaningful security holes that don't need spec changes.
4. **Reference strategy NAV bug** (`available_capital` vs `nav`) — three one-line fixes; reputation math is currently consuming wrong numbers.
5. **Circuit fixes**: short-side flip exit (#11), self-swap constraint (#12), range checks on slippage inputs (#13). Ideally batched into one rebuild + verifier redeploy + TAV class-map rotation.
6. **Bounded buffers + DB-shaped fixes** in services (oracle nonce sync, reputation pending, allocator events).
7. **Subgraph `capitalDeployed` semantics**, frontend `ActivityRail` key, `helios.conf` TLS — independent and parallelizable.
8. Hygiene/dead-code/CI caching in a single sweep PR.

---

## Surface coverage

| Surface | Files reviewed | Findings |
|---|---|---|
| Solidity contracts | `contracts/src/*.sol` (11 contracts + 3 verifier adapters + interfaces) | ~30 |
| Circom circuits | `circuits/{momentum_v1,mean_reversion_v1,yield_rotation_v1}.circom` + tests + fixture scripts | ~19 |
| Python services | `services/{sentinel,helix,reputation,oracle,prover,bot}` | ~30 |
| SDK / CLI / reference strategies | `packages/{strategy-sdk,allocator-sdk,helios-cli,contracts-abi*}` + `reference-strategies/*` | ~25 |
| Frontend | `frontend/src/{app,components,hooks,lib,styles}` | ~25 |
| Subgraph / deploy / CI / scripts | `subgraph/`, `deploy/`, `.github/workflows/`, `scripts/`, `scenarios/` | ~20 |

No CRITICAL findings in subgraph/deploy/CI. No live secret-leak vectors in SDK/CLI. Pinned addresses (UserVault, AllocatorVault, registries, TAV, Reputation V1/V2, oracle anchors), Goldsky pin (graph-cli 0.83.0 / graph-ts 0.31.0 / apiVersion 0.0.7), and snarkjs pin (0.7.6) all match CLAUDE.md and project memory.
