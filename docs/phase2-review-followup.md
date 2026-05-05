# Phase 2 review — follow-up pass (post-fixes)

Reviewed 2026-05-05, after the priority-1→5 punch list in `docs/phase2-review.md` landed (PRs through `543e1f0`). Each item is a real defect that *survives* the prior pass, plus newly-surfaced gaps and any regressions introduced by the fixes themselves. Refs are `file:line`.

The good news: the headline items from the prior review **did land**. Oracle-root validation, YR `strategy_vault` / `params_hash` / `markets_allowlist_root` PIs, calldata binding, NAV EIP-712, `commitInitialParamsHash` mandatory, MockSwapRouter relocation, `_isUniverseAsset` mapping, `_strategyDeployed` mirror retired, sentinel `[PASSPORT-STUB]` server verification, CORS tightened, `paramsRotations` Goldsky query + subgraph wiring, oracle scheduler atomic `snapshot_window`, reputation incremental fetch + score cache, sentinel `/v1/strategies` cache, backtest deque, signed `position_for`, NAV-aware sizing, MR signal-flip in `TradeIntent`, `proof_score_is_binary` flag, math.isclose weight invariant, `RECEIPT_TIMEOUT_SEC` shared util, deactivate cancels pending rotation — all verified in code.

Below is what is left.

---

## 🔴 Critical — fix before Phase 3 lands

### Oracle anchor scheduler nonce is not synced to chain

`services/oracle/src/oracle/anchor.py:265, 310, 326, 361` — `PriceAnchorScheduler._nonce` and `YieldAnchorScheduler._nonce` start at 0 in-process and increment **per `_prepare()` call**, not per successful submit. Two compounding failures:

- **Restart bug.** After a process restart `_nonce` resets to 0 while the on-chain `OraclePriceAnchor.nonce()` continues from N. Every signed commit thereafter recovers a non-`oracleSigner` address → `InvalidSigner` revert. Continuous-signing soundness is broken across any service crash.
- **Failure-poisoning bug.** `_prepare` increments `_nonce` even when the subsequent `poster.post()` raises; the next `_prepare` pre-increments again so the off-chain stream skips a nonce while on-chain stays put. A single transient RPC failure permanently desynchronizes the two streams.

Fix: read `IOracleAnchor.nonce()` on `_ensure_live` and again on each retry; or move the increment into `AnchorPoster.post()`'s success branch. Phase 2 e2e didn't catch this because it deploys fresh and submits without retries.

### Sentinel on-chain calls block the asyncio event loop

`services/sentinel/src/sentinel/onchain.py:233-235, 168-194` — `OnChainRunner._submit` is sync and ends in `wait_for_transaction_receipt(timeout=30)`. It is invoked from `SentinelLoop._apply_diffs` (sync wrapper) which is itself called from the async `_tick_user → tick_once → _run` chain. **Same bug as the prior review's oracle/reputation finding** (item 10), but the sentinel runner was missed. On a 1s-block chain this freezes the WS fanout to every `/v1/users/{user}/events` subscriber + the drawdown poll for up to 30s per emitted call. Mirror the `post_async = asyncio.to_thread(self.post, …)` pattern from `oracle/anchor.py:212-217`. While here, also dedupe `_RECEIPT_TIMEOUT_SEC = 30` (`onchain.py:45`) into `_template.web3_consts.RECEIPT_TIMEOUT_SEC` — the prior review's item 11 deduped oracle + reputation but skipped sentinel.

### Subgraph is missing every Phase-2 event

`subgraph/subgraph.yaml` is still the Phase-1 manifest. None of the following are indexed:

- **`StrategyVault.YieldRotationAttested`** — there is no handler in `subgraph/src/strategy-vault.ts`. Every YR attestation is invisible to Goldsky → reputation engine sees zero trades for YR strategies → score is permanently the cold-start floor.
- **`ReputationAnchorV2`** as a datasource — V2 is deployed by `DeployPhase2.s.sol` but the subgraph still binds the V1 address `0x51c07adf…`. `ComponentsAnchored` is never emitted into `ReputationSnapshot`, so the audit page can't render an on-chain componentsHash check.
- **`OraclePriceAnchor.Committed` / `OracleYieldAnchor.Committed`** — no datasources. Roots-known-on-chain is invisible to the dashboard.
- **`StrategyRegistry.MarketAllowlistRootSet`, `ParamsHashCommitted`, `ParamsRotationInitiated`, `ParamsRotationCancelled`** — no handlers in `strategy-registry.ts` (only `ParamsRotated` was added). The audit page can't render the rotation timeline because pending/cancelled states don't surface.
- **Multi-vault binding.** `subgraph.yaml:107-108` indexes a single `StrategyVault` address (`0x818a782f…` — Phase-1 momentum). `RegisterPhase2Strategies.s.sol` deploys a *second* vault per class plus a fresh-momentum vault for cold-start (TODO.md acceptance row 301: 7 vaults, only 1 indexed). 6 of 7 vaults emit events into `/dev/null` from Goldsky's perspective. This is the load-bearing reason Phase 2's reputation cohorts don't actually populate when consuming from a real subgraph — `test_engine.py` mocks Goldsky, so CI never noticed.

This single item invalidates two Phase 2 acceptance criteria (TODO.md:302 + the reputation engine being live against Goldsky). Phase 3 sits on top of it.

### ~~`RegisterFreshStrategy.s.sol` broadcast is uncommitted~~ — RESOLVED

Investigated 2026-05-05: the three uncommitted run-latest.json files are anvil-local e2e runs (block heights 0xa/0xe/0x12), not live Kite testnet deploys (compare Phase 1 at block 0x14191d0). Phase 2 has not yet been deployed to testnet. Resolution: extended `contracts/.gitignore` to exclude the e2e-only script directories so future local runs don't generate dirty-tree noise. When Phase 2 lands on testnet, drop the gitignore exclusion and commit the run-latest.json. Phase 2 acceptance row 232 is *not* satisfied yet — flagged in TODO.md follow-up.

---

## 🟡 High — soundness, distribution, frontend integrity

- **Reputation engine `since` is a global laggard.** `engine.py:120-122` uses `since = max(cutoff, min(all_hwms))`. A newly-registered strategy with backdated NAV/trade events (≤ 90d ago but > the laggard's HWM) has those events silently dropped — the cache only grows from `>` HWM forward (`engine.py:173-174`). Switch to per-strategy `since`, or always pull full-90d for any strategy whose `_cache_trade_hwm` is unset.

- **YR circuit still has no `block_window_start` PI.** `circuits/yield_rotation_v1.circom:109-111`, `contracts/src/StrategyVault.sol:383`. Pre-attested proofs from block 0 to `windowEnd` remain replayable across the entire pre-attestation window. Listed as priority 4 item 13 in `docs/phase2-review.md` and not addressed by `903fdb3`. Either add the PI + circuit window-bound check (mirror momentum's `windowDelta ≤ 100`) or document the explicit decision to defer.

- **Range checks missing on circuit price/threshold inputs.** `circuits/momentum_v1.circom:148-167, 195-207` and `mean_reversion_v1.circom:138-167` multiply `signal_threshold * price_first` and `(price_last - price_first) * 10000` without any prior `Num2Bits` on `price_observations[i]` or `signal_threshold`. In BN254 these wrap, and `Num2Bits(192)` on `long_excess` only catches values that *don't* coincidentally fit in 192 bits. Probabilistic gap (≈ 2⁻⁶²), but a malicious operator with prover access can grind for inputs that pass. Add intake range checks: `price_observations[i] : Num2Bits(64)`, `signal_threshold : Num2Bits(32)`, `stop_loss_price : Num2Bits(64)`. YR already does this for APY (`yield_rotation_v1.circom:190-197`).

- **`StrategyRegistry.slash` doesn't deactivate a zero-stake strategy.** `contracts/src/StrategyRegistry.sol:184-194`. Owner can slash to zero stake without setting `active=false`; allocator vault's `_checkStrategyRegistered` only rejects on `!s.active`. A zero-stake-but-active strategy can keep collecting allocations. Symmetric finding in `AllocatorRegistry.slash:185-195`. Add `if (s.stakeAmount == 0) s.active = false;` in both.

- **`AllocatorVault._checkMetaStrategyBounds` ignores `maxCapital` and `maxStrategies`.** `contracts/src/AllocatorVault.sol:352-375`. Only the per-strategy cap is enforced; the meta's *aggregate* cap and max-strategy-count are not. `MetaCapacityExceeded` (`:82`) and `MetaMaxStrategiesExceeded` (`:84`) are declared and never reverted with — they are dead code masquerading as enforcement. Either implement the checks or remove the errors and update the meta-strategy spec.

- **`StrategyVault.reportNAV` has no upper bound on NAV.** `contracts/src/StrategyVault.sol:518-530`. A compromised `navOracle` can set `_totalNAV = type(uint256).max`; the next `_navOf` (`:592`) computes `_totalNAV * _allocationOf[allocator]` which overflows and reverts, DoS'ing every read of the strategy. Cap to a sane multiple of `_manifest.maxCapacity` (e.g. `≤ 10 × maxCapacity`).

- **YR witness builder imports a workspace-only module.** `reference-strategies/yield_rotation_v1/src/yield_rotation_v1/witness.py:22` — `from oracle.poseidon import poseidon_hash`. Documented in TODO.md as Phase 3 work, but a contributor who installs `helios-yield-rotation-v1` from PyPI today has no `oracle` package available. Same module also rolls its own `_address_to_field` (`witness.py:198-203`) instead of `helios.poseidon.address_to_field` — the two encodings disagree on non-`0x`-prefixed inputs (latin-1 byte encoding vs field-element parse), so a strategy that mixes symbol form addresses across momentum vs YR will produce different `allocator_field` digests. Lift Poseidon into the SDK now (the deferred ticket TODO.md:227 → 338) or stop calling YR's witness builder a public surface.

- **e2e_scenario_phase2.py does not exercise the SDK witness builders.** `scripts/e2e_scenario_phase2.py:64-79` still imports `_phase2_witness.py`, the private rewrite. The SDK-side `momentum_v1/witness.py` and `mean_reversion_v1/witness.py` were fixed (real Poseidon completions, `strategy_vault`/`params_hash` PIs) but no scenario actually pushes those through the prover. Phase 2 acceptance row 304 is verified by SDK unit tests against `gen-fixture-*.js`, not by an integration run. Either retarget the e2e at the SDK builders, or delete `_phase2_witness.py` and force the issue.

- **NAV EIP-712 signer is not declared `immutable`.** `contracts/src/StrategyVault.sol:89` (`address public navOracle;`) is plain storage. There is no setter today, but a future UUPS upgrade could add one without anyone noticing the trust-model regression. Either mark `immutable` (won't survive UUPS, but at least catches the intent) or add a `setNavOracle(onlyOwner)` that emits an event — silent rotation through an upgrade is the worst of both.

- **Frontend audit page does not surface `proof_score_is_binary`.** `frontend/src/app/audit/[actor]/page.tsx:152-158`, `frontend/src/components/audit/ComponentBreakdown.tsx`. The reputation service exposes the flag (`services/reputation/src/reputation/service.py:225`), but the UI renders the `proof = 1.0` cell as a clean "verified" without the caveat the prior review explicitly added the flag to surface. Wire the boolean through `AuditPayload` and render a `(binary in v1)` annotation.

- **`OraclePriceAnchor` has no expiry / revoke.** `contracts/src/OraclePriceAnchor.sol:119-121`. `isKnownRoot(root)` returns true forever once committed. If `oracleSigner` is rotated under suspicion of compromise, the previously-attested roots stay valid for any future trade that wants to claim them. Add `revokeRoot(bytes32) onlyOwner` or a per-root expiry timestamp.

- **MR `_apply_intent` can stack positions on flip.** `packages/strategy-sdk/src/helios/backtest.py:347-376`. The strategy now correctly emits `is_signal_flip` flags, but the backtest still accumulates `qty` across direction changes (`new_qty = prev_qty + qty`) without first closing. A LONG at +5 followed by a SHORT signal applied as `qty=-3` yields a +2 long, not a -3 short. Documented in TODO.md:336 as a Phase 3 follow-up — flag here so reviewers don't expect Phase 2 backtest reports to reflect signal-flip semantics correctly.

- **Sentinel `_apply_diffs` always defunds on negative delta.** `services/sentinel/src/sentinel/loop.py:231-248`. Comment admits "Phase 1 collapses both [partial decrease and full removal] to a defund call". Phase 2 ships rebalance via `OnChainRunner.rebalance`, but the diff path never calls it — every weight decrease becomes a full defund. Either route deltas through `rebalance(weights_bps)` or document that partial-decrease is intentionally degraded.

- **Reputation V2 is wired but unused.** `contracts/src/ReputationAnchorV2.sol:171-181`. V2's `_applyUpdate` calls `strategyRegistry.updateReputation(actor, delta)`, but both registries gate that on `msg.sender == reputationAnchor` where `reputationAnchor` is **immutable** at registry construction (`StrategyRegistry.sol:19`). After `setRegistries(V2)`, V2's first `postReputationUpdate` will revert with `NotReputationAnchor` because the registry's immutable still points at V1. The TODO.md note (`project_reputation_phase1_simplified`) calls this Phase 5 work, but the *failure mode* should be visible: the first call to V2 reverts, not silently no-ops. Add a short-circuit `if (address(strategyRegistry) == address(0) || msg.sender-via-staticcall) return;` or document the v1→v2 cutover path explicitly.

---

## 🟠 Performance

- **`AllocatorVault._checkMetaStrategyBounds` walks `allowedStrategyClasses` linearly.** `contracts/src/AllocatorVault.sol:367-374`. Same fix pattern as the `_isUniverseAsset` mapping (perf item 19 in the prior review): populate a `mapping(bytes32 => bool) classAllowed` at `setMetaStrategy` time and read it in O(1). Saves ~1.5k gas per `allocateToStrategy` when N≥4 classes.

- **Reputation engine rebuilds cohort context against full-window sharpes even when the strategy itself is post-rotation.** `engine.py:137-138` builds `cohort_by_class` from `sharpes_by_strategy` (full 90d). `_compute_update:232-243` then *replaces* the per-strategy sharpes with a post-rotation slice, but normalizes against the unmodified cohort median. A rotated strategy compares its 7d post-rotation sharpe against a cohort median computed over its own pre-rotation 7d. Move the post-rotation slice up into `_windowed_sharpes` so cohort + per-strategy use the same input.

- **`_phase2_witness.py` re-imports `oracle.poseidon` per call.** `scripts/_phase2_witness.py:25-33` mutates `sys.path` then imports. If the e2e calls into it on every bar, the hot path crosses a `sys.path.insert` + `importlib._bootstrap` per call. One-time import at module top would be cleaner; better still, kill the script (see High item above).

---

## ⚫ Dead code (safe deletes)

- **`reference-strategies/{momentum_v1,mean_reversion_v1}/strategy.py` `set_capital`/`set_position` shadows.** Prior review flagged these as identical-shadows. They're not — `set_capital` now also calls `_set_nav` (which the SDK base does not). They're test seam aliases, not dead code, but the review-doc note in `docs/phase2-review.md:95` is now stale. Update the doc note rather than the code.

- **`witness.py` `position_state` field is consumed by no circuit.** `reference-strategies/momentum_v1/.../witness.py:155, 219` — `inputs["position_state"] = …` is forwarded to the prover. `momentum_v1.circom` has no `signal input position_state`. snarkjs ignores unrecognized inputs; nothing breaks, but the field has carried zero meaning since the v2 PI layout. Drop the field from the witness dict and from `runtime.py:219`.

- **`scripts/_phase2_witness.py` is a private substitute for shipped SDK.** `scripts/_phase2_witness.py` exists because the SDK builders were broken. They aren't anymore. The script's own docstring acknowledges "the logic here should graduate into the strategy-sdk". Either graduate (remove the `sys.path.insert` shim and import `from helios.classes.momentum_v1 import build_momentum_witness`) or delete the script — keeping both is the worst-of-both.

- **`StrategyVault.NotAllocatorVault` and `IStrategyVault.AssetNotInUniverse`.** Prior review item flagged both as never-reverted. `NotAllocatorVault` is now wired (`StrategyVault.sol:211`), but `IStrategyVault.AssetNotInUniverse` (`contracts/src/interfaces/IStrategyVault.sol`) remains unused — replaced by `AssetIndexOOB` in the runtime path. Drop the unused interface error.

- **`_strategyDeployed_deprecated` and `_metaSignatures_deprecated` storage slots.** `AllocatorVault.sol:65-66` and `UserVault.sol:57`. These are intentionally retained for UUPS storage-layout compat, with comments. Not dead — keep, but verify nothing in `forge inspect storage-layout` regressed.

- **`scripts/_phase2_oracle_nav.py` and `_phase2_reputation_local.py`.** These remain part of the e2e harness (driven by `scripts/e2e_scenario_phase2.py`). Not dead. Phase 3 should fold them into `services/oracle` and `services/reputation` test fixtures so the harness shrinks.

---

## Suggested order of operations

### Priority 1 — operational soundness (blocks Phase 3 going live)
1. Oracle scheduler nonce sync (Critical #1) — restart + retry desync is a permanent oracle-down condition in production.
2. Sentinel on-chain `to_thread` wrapping (Critical #2) — every demo call freezes the WS rail.
3. Subgraph datasource expansion (Critical #3) — the reputation engine + frontend are flying blind on 6 of 7 vaults.
4. ~~Phase-2 broadcast artifacts committed or retracted from gitignore whitelist (Critical #4)~~ — RESOLVED.

### Priority 2 — correctness & soundness
5. YR `block_window_start` PI (High).
6. Range-check intake on momentum/MR circuits (High).
7. `slash` deactivates at zero stake (High).
8. `_checkMetaStrategyBounds` aggregate caps + max-strategies enforcement (High).
9. NAV upper bound in `reportNAV` (High).
10. Reputation engine per-strategy `since` (High).

### Priority 3 — distribution & UX
11. Lift `oracle.poseidon` into SDK; YR witness uses SDK (High).
12. e2e_scenario_phase2 retargeted at SDK builders OR `_phase2_witness.py` deleted (High).
13. Frontend renders `proof_score_is_binary` (High).
14. Sentinel `rebalance` for partial decreases (High).
15. ReputationAnchor V1↔V2 cutover documented or short-circuited (High).

### Priority 4 — cleanup
16. `OraclePriceAnchor.revokeRoot` (High, optional).
17. `_checkMetaStrategyBounds` allowedStrategyClasses mapping (Perf).
18. Reputation cohort built against post-rotation sharpes (Perf).
19. `position_state` witness field removed (Dead).
20. `IStrategyVault.AssetNotInUniverse` removed (Dead).
21. `docs/phase2-review.md:95` shadow-method note updated (Dead/doc drift).

---

## Notes on what is *not* in this list

- Items already-deferred in `TODO.md` Deferred §: Telegram bot, x402, Helix regime/correlation, bespoke d3 sunburst, /docs, Echidna.
- Phase 4 enforcement of WS7.C TWAP/bond/confirm-window — meta-strategy fields ship in Phase 2 by design (TODO.md:288-292), implementation is Phase 4.
- Phase 5 V1↔V2 reputation registry redeploy — already tracked.
- Phase 6 Slither/Mythril clean — already tracked.
