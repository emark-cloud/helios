# Phase 2 review — gaps, bugs, security, perf, dead code

Reviewed 2026-05-04, post-Phase-2 landing. Each item is a real defect, not a deferred-Phase issue, unless flagged. Refs are `file:line`.

---

## 🔴 Critical — fix before Phase 3 lands more code on top

### Trust model is currently broken for `yield_rotation_v1`

The YR class as deployed is functionally an "operator just says they did the right thing" surface. Three independent gaps compound:

- **C-1. `StrategyVault` never validates oracle root against `OraclePriceAnchor` / `OracleYieldAnchor`.** `_validateAndVerify` (`contracts/src/StrategyVault.sol:242-274`) and `_validateAndVerifyYR` (`:276-293`) treat `PI_*_ORACLE_ROOT` as proof input only — `grep -rn isKnownRoot src/` is empty. An operator can mint a Poseidon root over fictitious prices. Spec §9.3 is unimplemented.
- **C-2. YR proof has no `strategy_vault` binding → cross-vault replay.** `circuits/yield_rotation_v1.circom:202-214` builds `trade_hash` without `strategy_vault`. Two YR vaults under one allocator can replay each other's freshly-attested proofs. Momentum (`circuits/momentum_v1.circom:213`) and MR (`mean_reversion_v1.circom:239`) don't have this gap.
- **C-3. YR `markets_allowlist_root` and `signal_threshold` are private witnesses.** `TODO.md:273-277` acknowledges this as a "v2 circuit change" — but it's an attestation hole *now*: operator can claim any threshold/bridging-cost/allowlist at proof time. `StrategyRegistry.setMarketAllowlistRoot` is read by nothing on the trade path.

### Trade calldata is not bound to the proof (all classes)

`StrategyVault._runTrades` (`StrategyVault.sol:309-317`) accepts arbitrary `Call[]` from the operator. `c.target` is universe-asset-checked, but `c.data` is not. `c.data = transfer(operator, balance)` clears the vault — USDC is a universe asset. The proof attests intent metadata; execution is unconstrained. This contradicts the §6.4 trust constraint that ZK gates trade execution. Operator's stake is forfeit, but loss > stake is possible.

### Reputation engine is broken against a real subgraph

- **R-1. `services/reputation/src/reputation/goldsky.py:53-60`** queries `Strategy.paramsRotations`, which doesn't exist in `subgraph/schema.graphql:40-57`. Goldsky returns a query error → `engine.tick_once()` swallows it → `[]` strategies → no scores ever update. Tests don't catch this because `test_engine.py` mocks Goldsky. The moment Phase 2 e2e flips to a live subgraph, scoring is dark.
- **R-2.** Even with R-1 patched, the WS7.A reset code at `engine.py:170-181` is dead: `ParamsRotated` isn't indexed (no handler in `subgraph/src/strategy-registry.ts`), so `last_rotation_epoch` is always 0. Track records accumulate across rotations — exactly the failure mode §9.3 warns about.

### Sentinel REST endpoint hijacks any user's meta-strategy

`services/sentinel/src/sentinel/service.py:131-155` `POST /v1/users/{user}/meta-strategy` records the supplied `signature` field but never verifies it (`schemas.py:40` comment is an IOU). `services/_template/app.py:49` ships `allow_origins=["*"]`. Any browser tab can rewrite any user's allocation policy server-side. Phase 1's `[PASSPORT-STUB]` produced an EOA `personal_sign` — at minimum verify that until Phase 4's Passport rebuild lands.

### Reference-strategy witness builders don't match the circuits

`reference-strategies/momentum_v1/src/momentum_v1/witness.py:90-122` and `mean_reversion_v1/src/mean_reversion_v1/witness.py:101-114,127-131` ship dictionaries the circuit will reject:

- Missing `strategy_vault`, `params_hash` keys; uses `asset_in`/`asset_out`/`asset_universe[]` instead of `asset_in_idx`/`asset_out_idx`.
- Pass `oracle_root="0"`, `trade_hash="0"`, `params_hash="0"` with a `pending_poseidon=…` hint. The prover (`services/prover/src/index.js:68-89`) does **not** complete those — it forwards verbatim to snarkjs.

Phase 2 e2e dodges this with a private `scripts/_phase2_witness.py` (whose docstring confirms the shipped builders are broken). Net effect: the Phase 2 acceptance criterion "external contributor could ship a strategy" is false. `helios test-proof` against a freshly-installed `helios-strategy-sdk` will not produce a verifying proof for momentum or MR.

### Oracle anchor scheduler — torn read

`services/oracle/src/oracle/anchor.py:262-286` calls `store.recent(asset, n)` then `store.chain_root(asset, n)` as separate locked operations. A poller append between them produces a committed root that doesn't correspond to the prices a circuit would reproduce → intermittent on-chain proof rejections. Same race in `YieldAnchorScheduler`. Fix: single `snapshot_window(n) -> (snaps, root)`.

### Blocking sync I/O on the asyncio loop

`oracle/poller.py:104` calls `_on_snapshot` which chains into Web3 RPC (`AnchorPoster.post`) — blocking sync HTTP calls including a `wait_for_transaction_receipt(timeout=30s)`. The whole oracle service freezes for up to 30s every `interval_bars` snapshots: price polling, yield polling, FastAPI WS clients all stall. Same shape in `services/reputation/src/reputation/anchor.py`. Wrap with `asyncio.to_thread`.

### `helios stake top-up` signs and broadcasts with no confirmation

`packages/helios-cli/src/helios_cli/strategy.py:362-388`. `--dry-run` is opt-in. Typo in `--strategy-id` or `--amount` → irrevocable on-chain tx with no y/N. Industry baseline is the inverse default.

### `helios deploy --vps` is option-injectable

`packages/helios-cli/src/helios_cli/strategy.py:292,297` — `subprocess.run(["ssh", target, …])` with attacker-controlled `target` like `-oProxyCommand=/tmp/x` runs arbitrary commands. Add `--` after `ssh`.

---

## 🟡 High — spec gaps & soundness

- **NAV signature lacks EIP-712 framing.** `StrategyVault.reportNAV` (`:344-355`) recovers from a 4-tuple of `(chainid, address(this), nav, ts)`. No domain separator, no typehash. Cross-context replay risk if the same key is reused. Switch to EIP-712 `NAVUpdate`.
- **`commitInitialParamsHash` is bypassable.** Operator can `registerStrategy` and trade indefinitely against `_manifest.paramsHash`; never calling `commitInitialParamsHash` keeps the rotation flow inert (`StrategyVault.sol:394-398`). Either reject trades until commit, or remove the manifest fallback.
- **YR has no `block_window_start` PI.** Momentum/MR enforce `windowEnd - windowStart ≤ 100`. YR proofs are valid from block 0 to `windowEnd`. Pre-attested proofs sit indefinitely.
- **`ReputationAnchorV2` deployed but registries still wired to V1.** Both registries' `reputationAnchor` is `immutable`. V2's `ComponentsAnchored` event fires, but `currentReputation` continues reflecting V1 only. CLAUDE memory `project_reputation_phase1_simplified` already tracks this for Phase 5 — flagging because the audit page can render misleading "verified" components against a stale aggregate.
- **`ProofScore` is binary 0/1 but `/v1/audit` exposes it as `1.0` with no caveat.** Frontend will render "all proofs valid" when the actual signal is "no rejected proofs are observable." Add `proof_score_is_binary: true` to the audit payload.
- **MR signal-flip flags race across assets.** `mean_reversion_v1/strategy.py:80-87` resets instance-level `_last_is_stop_loss` flags every `on_bar`. Multi-asset ticks can clobber the flag a different asset's runtime needs. Move flags into the returned intent.
- **`StrategyAgent.position_for(asset)` returns absolute qty.** `agent.py:96-98` — backtest stores `holdings[asset] = -qty` for shorts but `_set_position(asset, abs(new_qty), …)`. `if self.position_for(asset) < 0: ...` is silently always-false. Footgun for SDK consumers.
- **`helios backtest` produces a clean zero-trade report for `YieldRotationStrategy`.** No warning, no error. Confirmed in `packages/strategy-sdk/src/helios/backtest.py:132` (only iterates `asset_universe`, which YR sets to `()`).
- **Sizing on stale cash, not NAV.** `momentum_v1/strategy.py:78-82`, `mean_reversion_v1/strategy.py:145-149` size on `available_capital` (cash component only). A 90%-deployed strategy sizes new entries off 10% cash. Backtest reports under-state real position size.
- **`assert weights == 1.0`** in `services/reputation/src/reputation/score.py:44` uses `==` on floats. Currently exact in IEEE-754, but a future tweak will silently break. Use `math.isclose`.
- **`OraclePriceAnchor` window doc says `(start, end]` but contract enforces `[start, end]`** (`OraclePriceAnchor.sol:17-19`). Comment drift.
- **`StrategyRegistry.deactivate` doesn't cancel a pending `paramsRotation`.** Completing rotation post-deactivate still mutates the active hash.

---

## 🟠 Performance

- **`_isUniverseAsset` linear scan** (`StrategyVault.sol:407-413`) per trade × call. Replace with `mapping(address=>bool)` set at `initialize`. ~2.1k gas/call when N≥4.
- **`_strategyDeployed` mirrors `_allocations[user][s].capitalDeployed`** (`AllocatorVault.sol:58, 138-139, 191-198, 299-311`). Eliminating the duplicate saves ~5k gas / strategy / rebalance.
- **Reputation `tick_once` re-fetches the full 90d window every 60s for every strategy.** Track high-water timestamp per strategy; pull incrementally; keep 90d window in memory.
- **`/v1/strategies` re-queries Goldsky on every request** (`services/sentinel/src/sentinel/service.py:164-171`). `SentinelLoop._refresh_candidates` already maintains a 5-min cache (`loop.py:100-108`). Reuse it. ~10–100× latency win on dashboard loads.
- **Backtest `window = list(prices[asset][window_lo:bar+1])`** rebuilt every bar (`packages/strategy-sdk/src/helios/backtest.py:136`). `collections.deque(maxlen=lookback)` is a one-line fix; ~30% speedup on 180d runs.
- **Score recompute every tick** (`reputation/score.py:239-256`). Cache `keccak(abi_encode(...))` by component-tuple; avoid re-hashing identical components.
- **Momentum/MR oracle root chain uses 16 sequential Poseidon hashes** (~1.5k constraints each). Switching to a depth-4 Merkle proof recovers ~20k constraints under PTAU 16. Optional but useful headroom.

---

## ⚫ Dead code (safe deletes)

- **`contracts/src/mocks/MockSwapRouter.sol`** — sits in `src/`, not `test/mocks/`. Could ship to mainnet by accident. Move.
- **`StrategyVault.NotAllocatorVault` error** — ~~declared, never reverted with~~. Wired in `StrategyVault.sol:211` (followup #20).
- **`IStrategyVault.AssetNotInUniverse` error** — ~~never thrown~~. Removed from the interface; the runtime path now reverts with `StrategyVault.AssetIndexOOB` (followup #20).
- **`UserVault.settleAllocatorFee`** (`:172-178`) — bumps HWM, emits, no value movement. Comment admits no-op. Either remove from public ABI or land real settlement.
- **`UserVault._metaSignatures` mapping** (`:53`) — written by `setMetaStrategy` (`:123`), never read. Storage slot already burned. Drop the write or read it.
- **`packages/helios-cli/src/helios_cli/strategy.py:183,187`** — `cum` assigned, overwritten, never read.
- **`packages/helios-cli/src/helios_cli/strategy.py:228-238`** — `plan` stringified preview duplicates `_execute_deploy` logic and uses misleading shell syntax (`scp <(printf …)` vs the real `ssh target 'cat > …'`). Drop or unify.
- ~~**`reference-strategies/{momentum_v1,mean_reversion_v1}` `set_capital`/`set_position`** shadowing the SDK base hooks with identical impls minus the underscore.~~ Followup #21: not identical-shadows — `set_capital` also calls `_set_nav` (the SDK base does not). They are intentional test-seam aliases, kept.
- **`momentum_v1/runtime.py:190`** — `is_stop_loss=False` hardcoded; the strategy never raises one. Dead branch.
- **`reputation/score.py W_*` weights** redeclared in `service.py:203-209` and `docs/reputation-math.md`. Pick one source and import.
- **`reputation/anchor._RECEIPT_TIMEOUT_SEC`** duplicated in `oracle/anchor.py`. Move to a shared util.

---

## Suggested order of operations

### Priority 1 — security model integrity (block Phase 3)

1. **YR oracle-root validation** (C-1) — wire `OraclePriceAnchor.isKnownRoot` / `OracleYieldAnchor.isKnownRoot` into `_validateAndVerify` and `_validateAndVerifyYR`. Same patch fixes momentum + MR.
2. **YR `strategy_vault` binding** (C-2) — promote to public input, add to circuit Poseidon over `trade_hash`, vault-side equality check. Requires circuit recompile + new vkey + redeploy.
3. **YR `markets_allowlist_root` + `paramsHash`** (C-3) — promote both to public inputs; vault checks against `StrategyRegistry.marketAllowlistRoot(class)` and `paramsHashOf(strategyVault)`. Otherwise `setMarketAllowlistRoot` is decoration.
4. **Bind trade calldata to the proof** — either decode `Call.data` and compare `(asset_in, asset_out, amount_in, min_amount_out)` against PI fields, or restrict `data` to a small selector whitelist. Without this the ZK is theatre for execution.
5. **NAV EIP-712 framing** — quick win, defense-in-depth.

### Priority 2 — Phase 2 acceptance criteria are currently false

6. **Reference witness builders match the circuits** — momentum + MR `witness.py` need `strategy_vault`, `params_hash`, `asset_*_idx`, and the Poseidon completions (`oracle_root`, `trade_hash`, `params_hash`) computed in Python, not "pending". Cross-check bit-exact against `circuits/scripts/gen-fixture-mr.js` / `momentum.test.js`. Until this lands, Phase 2 acceptance "external contributor could publish a momentum strategy using only the SDK" is aspirational.
7. **Reputation engine `paramsRotations` query + subgraph indexing** — either drop the field from the query (and accept WS7.A reset is deferred), or land the `ParamsRotated` mapping in `subgraph/src/strategy-registry.ts` + schema. Right now the engine errors against any real Goldsky.

### Priority 3 — exploitable / demo-blocking

8. **Sentinel REST auth** — verify `[PASSPORT-STUB]` EOA `personal_sign` server-side; tighten `allow_origins`.
9. **Oracle scheduler torn-read** — `SnapshotStore.snapshot_window(n) -> (snaps, root)` under one lock. Same for `YieldStore`.
10. **Async-blocking I/O** — `asyncio.to_thread` around Web3 calls in `oracle/anchor.py` and `reputation/anchor.py`.
11. **CLI safety** — `helios stake` confirmation prompt by default; `ssh -- target` in `helios deploy`.

### Priority 4 — soundness fixes & dead code

12. `commitInitialParamsHash` mandatory or manifest fallback removed.
13. YR `block_window_start` PI.
14. `StrategyAgent.position_for` returns signed qty.
15. MR signal-flip flags moved into `TradeIntent`.
16. Sizing helper that re-sizes against current NAV (also cleans up TODO line 335).
17. Float-tolerant weight invariant + audit-payload `proof_score_is_binary` flag + comment-drift fixes.
18. Dead-code deletions (the list above).

### Priority 5 — performance pass once correctness lands

19. `_isUniverseAsset` mapping; drop `_strategyDeployed` mirror.
20. Reputation incremental window pulls + score-cache.
21. Sentinel `/v1/strategies` cache reuse.
22. Backtest `deque` rolling window.

---

## Notes on what is *not* in this list

- Items explicitly tracked as Phase 4/5/6 work in `TODO.md` (auto-defund TWAP/bond enforcement, Passport widget rebuild, x402 paid services, mainnet promotion, full Slither/Mythril/Echidna passes, allocator SDK + Helix) — these are scoped, not gaps.
- `reference_kite_contract_surface` memory items (no on-chain Pyth/Chainlink on Kite) — design constraint, not a defect.
- `project_subgraph_goldsky_wasm` pinning — known limitation honored by Phase 2 schema choices.

Three full per-surface review reports are in the conversation transcript that produced this digest, including individual item severity calls and the sub-agent verification trail.
