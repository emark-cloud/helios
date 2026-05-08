# Phase 4 — Frontend completion + signature interactions (plan)

**Status.** Drafted 2026-05-07. Phases 0–3 merged to `main`; this is the
implementation plan for Phase 4 per `TODO.md` lines 363–415.

**Goal (from `TODO.md`).** Every `DESIGN.md §9` surface shipped, the three
signature interactions (cascade / auto-defund / cross-chain rep update) land
visibly, the `[PASSPORT-STUB]` onboarding flow swaps to real Kite Passport,
and the contract-side defund + NAV-divergence paths that the auto-defund
moment depends on are enforced on-chain. Acceptance: Phase 1 scenario
replays at full visual fidelity; an external designer reviewing the live
app says "Bloomberg meets Vercel v0," not "DeFi app."

This plan is the source of truth for branch layout, PR shape, sequencing
and acceptance — equivalent to `docs/phase1-plan.md` / `docs/phase3-plan.md`
for prior phases.

---

## 1. Source documents

- `Helios.md` §6.3 (`AllocatorVault.defundStrategy` numerical pinning),
  §6.4 (`StrategyVault.reportNAV` NAV-divergence slash),
  §6.10 (`OraclePriceAnchor.freshness()`), §10 (meta-strategy fields),
  §13 (frontend surfaces), §14.1 (demo voiceover, passkey),
  §15 (threat model — passport posture).
- `DESIGN.md` §4.3 (color), §4.5 (density split), §5.5 (keyboard),
  §9.1/9.5/9.7/9.8 (remaining surfaces), §10 (signature interactions),
  §11 (sunburst v1 scope note), §12 (ZK celebrated treatment),
  §13 (motion budget), §14.3 (a11y), §14.5 (perf), §15 (event message style).
- `docs/kite-passport-integration.md` (Choice C + E + F) and
  `docs/kite-passport-notes.md` (Patterns 1–3 + locked SDK versions).
- `TODO.md` Phase 4 section + relevant Phase 2/3 deferrals
  (lines 290–293, 396–397).

When the docs disagree with code-as-built, the docs win — but log the
deviation in `TODO.md`.

---

## 2. Workstream map

Nine workstreams. Tracks roughly correspond to subsystems and run with
the dependencies in §3.

| WS | Track | Branch | Owner area | Headline |
|---|---|---|---|---|
| **WS-CX-1** | Contracts | `phase-4-contracts-defund` | `contracts/src/AllocatorVault.sol` | TWAP-persistence + bond + confirm-window for `defundStrategy` |
| **WS-CX-2** | Contracts | `phase-4-contracts-navdiv` | `contracts/src/StrategyVault.sol` | NAV-divergence detection emits `NavDivergenceObserved`; queues slash |
| **WS-SVC-1** | Services | `phase-4-sentinel-chainwatch` | `services/sentinel/` | Sentinel observes on-chain `Allocation*`/`StrategyDefunded`/`NAVReported` so dashboard rail mirrors chain |
| **WS-FE-1** | Frontend | `phase-4-passport-onboard` | `frontend/src/app/onboard/`, `frontend/src/app/providers.tsx` | Passport widget + AA SDK; one-passkey batched userOp; drop every `[PASSPORT-STUB]` |
| **WS-FE-2** | Frontend | `phase-4-fe-landing-judge` | `frontend/src/app/page.tsx`, `frontend/src/app/judge/` (new) | `/` landing rebuild + new `/judge` page |
| **WS-FE-3** | Frontend | `phase-4-fe-strategy-detail` | `frontend/src/app/strategies/[id]/` (new) | Strategy detail surface + manifest, P&L curve, recent trades, allocators, NAV timeline |
| **WS-FE-4** | Frontend | `phase-4-fe-audit` | `frontend/src/app/audit/[strategy]/` (new), retain `[actor]` | Forensic per-strategy audit page, celebrated ZK treatment, verify-yourself modal |
| **WS-FE-5** | Frontend | `phase-4-fe-sunburst` | `frontend/src/components/sunburst/` (new) | Concentric-ring viz (v1 simplified) + integration on `/dashboard` and allocator cards |
| **WS-FE-6** | Frontend | `phase-4-fe-signature-motion` | `frontend/src/components/dashboard/` + `motion/` (new) | Cascade, auto-defund (5–6s thermostat), cross-chain rep-in-flight |
| **WS-FE-7** | Frontend | `phase-4-fe-polish` | cross-cutting | Keyboard shortcuts, reduced-motion, focus rings, WCAG, projector, defund-bond UX, onboard error UX |
| **WS-ACC** | Acceptance | `phase-4-acceptance` | `scripts/`, `frontend/tests/` | Phase 1 scenario re-runs at full visual fidelity; Lighthouse re-measure; designer-review checklist green |

PR convention is unchanged from prior phases: `[Phase 4][<track>] <imperative>`.

---

## 3. Build order

The order is derived from these dependencies:

- **Auto-defund signature moment depends on chain-side correctness.** The
  thermostat-kicking-on visual is the Phase 4 headline (DESIGN §10.2),
  but if the chain still fires defund on a single transient bar — or
  doesn't slash on NAV divergence — the moment fires for the wrong
  reason. WS-CX-1 + WS-CX-2 must land before WS-FE-6 even though they
  feel "backend."
- **Activity rail truthfulness depends on Sentinel observing chain
  events.** Without WS-SVC-1, the rail lies during scenario runs.
  WS-SVC-1 lands before WS-FE-6.
- **Passport rebuild touches `providers.tsx`.** Every wallet-aware
  surface in subsequent WS reads from the same hook tree. WS-FE-1 lands
  before WS-FE-3..7.
- **The sunburst is consumed by `/dashboard`, the cascade animation,
  the allocator card mini-sunburst, and the defund rebalance step.**
  WS-FE-5 must land before WS-FE-6 (signature motion depends on it),
  and is most efficient if it lands before WS-FE-2..4 too because
  the concentric-ring component is reusable across `/strategies/[id]`
  (current allocators panel) and `/audit/[strategy]` (component
  breakdown reuse).
- **Pages without animation can ship in any order once the chrome is
  ready.** WS-FE-2/3/4 are roughly parallelizable.

The serial spine:

```
WS-CX-1 ──┐
          ├── WS-FE-6 (signature motion) ── WS-FE-7 (polish) ── WS-ACC
WS-CX-2 ──┤
          │
WS-SVC-1 ─┤
          │
WS-FE-1 ──┴── WS-FE-5 (sunburst) ─┬── WS-FE-2 (landing/judge)
                                  ├── WS-FE-3 (strategy detail)
                                  └── WS-FE-4 (audit)
```

Recommended single-developer order (top→bottom = ship in this order):

1. **WS-CX-1** — defund hardening
2. **WS-CX-2** — NAV-divergence slash path
3. **WS-SVC-1** — Sentinel chain-watcher
4. **WS-FE-1** — Passport onboarding rebuild
5. **WS-FE-5** — sunburst v1 component (no integration yet)
6. **WS-FE-3** — `/strategies/[id]` (uses sunburst's concentric-ring atom + recent-trades shield treatment that WS-FE-4 will reuse)
7. **WS-FE-4** — `/audit/[strategy]` (extends shield treatment, celebrated ZK)
8. **WS-FE-2** — `/` landing + `/judge` (smaller, last so subgraph live counts include the new surfaces)
9. **WS-FE-6** — signature interactions (cascade + auto-defund + xchain pulse)
10. **WS-FE-7** — keyboard, reduced-motion, focus, WCAG, projector, defund-bond UX, onboard error UX
11. **WS-ACC** — acceptance e2e + visual fidelity audit + Lighthouse re-gate + release tag

If two developers split work: dev-A takes WS-CX-1/2 + WS-SVC-1 + WS-FE-6
+ WS-FE-7 (the chain-aware spine), dev-B takes WS-FE-1 + WS-FE-5 + WS-FE-2
+ WS-FE-3 + WS-FE-4 (the static-surface spine). They converge at WS-ACC.

---

## 4. Workstream detail

### 4.1 WS-CX-1 — `AllocatorVault.defundStrategy` hardening

**Spec.** `Helios.md §6.3`. Numerical constants:

- `defundTwapBars` — default 3, range 1–24 (already in
  `MetaStrategyLib.DEFAULT_DEFUND_TWAP_BARS`).
- `defundBondBps` — default 50 bps of defunded notional.
- `defundConfirmBlocks` — default per `MetaStrategyLib`; bond
  refund window.
- `defundRewardCapUsd` — default $500; reward cap.
- `MAX_STALENESS_SEC` — 180s for the oracle-freshness gate.
- `MIN_BAR_BLOCKS` — 300 (≈5 min on Kite's 1s blocks). Minimum
  spacing between consecutive observations to prevent same-block
  spam from satisfying the persistence requirement.

**Spike outcome (2026-05-07, WS-CX-1.1).**

`OraclePriceAnchor` is an append-only ledger of Poseidon roots
(commit windows of off-chain price snapshots collapsed into a single
Poseidon root for ZK consumption). It does **not** expose per-asset
TWAP prices. There is no on-chain price oracle on Kite testnet/mainnet
(no Pyth/Chainlink). The spec text in `Helios.md §6.3` ("oracle-priced
asset universe (TWAP per OraclePriceAnchor)") describes capability the
deployed oracle does not ship.

Phase 4 adopts a **caller-cadence persistence design** instead:

- Drawdown is sampled from `IStrategyVault.navOf(address(this))` —
  the per-allocator NAV the StrategyVault tracks (operator-signed
  via `reportNAV`, gated by the WS-CX-2 NAV-divergence slash path
  for Sybil protection).
- Persistence is enforced by requiring `defundTwapBars` consecutive
  observations spaced ≥ `MIN_BAR_BLOCKS` apart. Each observation is
  a separate `triggerDefund` call.
- Oracle freshness is enforced via
  `block.timestamp - oracleAnchor.latest().committedAt <
  MAX_STALENESS_SEC` — a coarse "the oracle hasn't gone offline"
  gate, independent of asset prices.

A real per-asset TWAP path (e.g., reading from Algebra V3 pool TWAPs
on Kite mainnet, or a separate per-asset price-anchor service) is
deferred to v2 / post-hackathon (`Helios.md §17` Phase 1) — log this
deviation in the WS-CX-1 PR and a TODO entry under Phase 5 cross-chain.

**Existing state.** `AllocatorVault.defundStrategy` (lines 210–237) does
single-snapshot drawdown check only. Permissionless path computes
`ddBps` from current NAV and current HWM and reverts if below
`drawdownThresholdBps`. Bond, persistence, and confirm-window are not
implemented.

**Implementation.**

1. Add storage:

   ```solidity
   struct PendingDefund {
       uint64  firstObservedAt;     // block.timestamp of first observation
       uint64  firstObservedBlock;  // block.number of first observation
       uint64  lastObservedBlock;   // block.number of most recent observation
       uint8   breachCount;         // consecutive breach observations
       address triggerer;           // who posted the bond
       uint128 bondAmount;          // USDC posted, e6
   }
   mapping(address => mapping(address => PendingDefund)) public pendingDefunds;
   ```

2. Split the permissionless path into observation, finalize, and
   cancel. Operator path stays single-call.

   ```solidity
   function triggerDefund(address user, address strategy) external nonReentrant;
   function finalizeDefund(address user, address strategy) external nonReentrant;
   function cancelDefund(address user, address strategy) external nonReentrant;
   ```

   - **`triggerDefund`** runs in two modes:
     - *No pending entry:* check oracle freshness via
       `oracleAnchor.latest().committedAt`. Read
       `IStrategyVault.navOf(address(this))`, compute drawdown vs
       `strategyHighWaterMark`. If `ddBps ≥ drawdownThresholdBps`,
       transfer bond (`defundBondBps × capitalDeployed / 10_000`
       USDC) from `msg.sender` and record the pending entry with
       `breachCount = 1`. Emit
       `DefundObserved(user, strategy, triggerer, breachCount,
       observedDrawdownBps, bondAmount)`.
     - *Pending entry exists:* require
       `block.number ≥ lastObservedBlock + MIN_BAR_BLOCKS` (else
       revert `BarTooSoon`). Re-read NAV. If drawdown still ≥
       threshold: `breachCount++`,
       `lastObservedBlock = block.number`, emit `DefundObserved`.
       When `breachCount` hits `defundTwapBars`, emit
       `DefundArmed(user, strategy, lastObservedBlock)`. If
       drawdown recovered: clear the entry, refund bond to
       `triggerer`, emit `DefundCancelled(user, strategy,
       reason="RECOVERED")`. Anyone can advance the counter
       (not gated to the original triggerer).
   - **`finalizeDefund`** requires `breachCount ≥ defundTwapBars`
     (armed) and `block.number ≥ lastObservedBlock +
     defundConfirmBlocks`. Re-reads `navOf()`:
     - Drawdown still ≥ threshold → run `_unwindAndCredit(user,
       strategy)`, refund bond to `triggerer`, pay reward
       `min(defundBondBps × capitalDeployed / 10_000,
       defundRewardCapUsdE6, _accruedFees)` from
       `AllocatorVault._accruedFees`. *v1 reward-source
       deviation: spec text in `Helios.md §6.3` describes
       reward from strategy stake; v1 routes from allocator
       accruedFees because `StrategyRegistry` is immutable in
       Phase 3 — adding `payDefundReward` requires a full
       registry redeploy + re-registration of every strategy.
       v2 (post-hackathon Phase 1) restores stake-based
       reward via the registry rebuild already scheduled in
       §17 alongside slashing-dispute work.* If accruedFees
       are insufficient, reward is paid down to whatever is
       available; bond is always refunded in full.
       Emit `StrategyDefunded(...)` (existing shape) +
       `DefundFinalized(user, strategy, refunded, reward,
       slashedToUser=0)`.
     - Drawdown recovered → bond slashed to the user's
       `UserVault`. Emit `DefundFinalized(user, strategy,
       refunded=0, reward=0, slashedToUser=bondAmount)`.
     - Either branch clears the pending entry.
   - **`cancelDefund`** is operator-only — clears the pending
     entry and refunds the bond to `triggerer`. (Permissionless
     finalize already handles the offline-operator case via the
     "recovered" branch returning bond-to-user, so a separate
     permissionless cancel is unnecessary.)

3. **Events** (subgraph schema additions in `subgraph/schema.graphql`
   land separately in WS-SVC-1 / WS-FE-7's defund-bond UX work):

   - `DefundObserved(address indexed user, address indexed strategy,
     address indexed triggerer, uint8 breachCount,
     uint256 observedDrawdownBps, uint256 bondAmount)`
   - `DefundArmed(address indexed user, address indexed strategy,
     uint64 armedAtBlock)`
   - `DefundCancelled(address indexed user, address indexed strategy,
     bytes32 reason)` — `reason ∈ {"RECOVERED","OPERATOR_CANCEL"}`
   - `DefundFinalized(address indexed user, address indexed strategy,
     address triggerer, uint256 refunded, uint256 reward,
     uint256 slashedToUser)`
   - `StrategyDefunded` — keep existing shape (subgraph mapping
     unchanged).

4. **Tests** (`contracts/test/AllocatorVault.defund.t.sol`,
   extend or replace):

   - Single observation below threshold → revert
     `DrawdownNotBreached`, no pending entry created.
   - First observation breaches → bond pulled, pending entry has
     `breachCount = 1`, `DefundObserved` emitted.
   - Second observation < `MIN_BAR_BLOCKS` after first → revert
     `BarTooSoon`.
   - Three valid observations all breaching → `breachCount = 3 ==
     defundTwapBars`, `DefundArmed` emitted.
   - Mid-observation drawdown recovered → entry cleared, bond
     refunded to triggerer, `DefundCancelled("RECOVERED")`.
   - Stale oracle (`block.timestamp - latest().committedAt >
     MAX_STALENESS_SEC`) → revert `OracleStale` (only on the first
     observation; once armed the freshness gate is past).
   - Finalize before armed → revert `DefundNotArmed`.
   - Finalize before `lastObservedBlock + defundConfirmBlocks` →
     revert `ConfirmWindowNotElapsed`.
   - Finalize after window with breach still standing → bond
     refunded + reward paid from strategy stake; user principal
     unchanged; `_userTotalDeployed` decreases by capitalDeployed;
     `defundedAt` set.
   - Finalize with NAV recovered → bond slashed to user's
     `UserVault`, no reward, allocation NOT unwound.
   - Reward capped at `defundRewardCapUsd × 1e6` for very large
     allocations.
   - Operator `cancelDefund` → bond returned to triggerer, entry
     cleared.
   - Non-operator `cancelDefund` → revert `OnlyOperator`.
   - Operator-side `defundStrategy` (existing path) unchanged —
     bond/persistence/confirm-window not required, single-call
     unwind. Test the existing happy-path is preserved.

5. **Coverage gate.** Maintain ≥85% line coverage on
   `AllocatorVault.sol`; the new branches will pull aggregate up.

6. **ABI/subgraph.** Regenerate `packages/contracts-abi/`. Schema
   bump for `DefundTriggered` + `DefundFinalized` lands in
   subgraph/v0.2.x and gets deployed to Goldsky in WS-SVC-1
   (consumes them).

**Out of scope here.** Operator-key rotation, governance bond cap
parameter, and per-class TWAP cadence variance — all roadmap.

---

### 4.2 WS-CX-2 — NAV-divergence slash path

**Spec.** `Helios.md §6.4` (rewritten 2026-05-07) and `TODO.md` line 292.

**Audit outcome (WS-CX-2.1).** `OraclePriceAnchor` exposes Poseidon
roots only — no per-asset on-chain price reads. StrategyVault holds
`baseAsset` (USDC) plus optional non-USDC positions in `assetUniverse`
(post-swap). Without an on-chain price source we **cannot compute
markedNAV bidirectionally**, only a one-sided cash-floor lower bound:
`markedNAV_floor = baseAsset.balanceOf(strategyVault)`.

For the v1 long-only spot classes (`momentum_v1`, `mean_reversion_v1`,
`yield_rotation_v1`) the invariant `NAV ≥ cashHeld` is hard. So
`signedNAV < cashHeld - threshold` is unambiguous evidence of
**operator under-reporting** (an attack vector against drawdown calc
and fee crystallization). Phase 4 ships exactly this check. Operator
**over-reporting** (the spec's "suppress defund" vector) needs an
upper-bound recomputation against an on-chain price source — deferred
to v2 / post-hackathon (§17 Phase 1) along with the per-asset TWAP anchor.

**Implementation.**

1. New constant `NAV_DIVERGENCE_THRESHOLD_BPS = 500` on
   `StrategyVault.sol`, owner-settable.

2. New storage:

   ```solidity
   uint8 public consecutiveDivergenceBreaches;
   uint16 public navDivergenceThresholdBps; // 0 → DEFAULT
   ```

3. On every `reportNAV(signedNAV)`, after the existing signature/
   monotonicity/cap checks land the new total NAV:

   ```
   markedFloor = baseAsset.balanceOf(address(this))
   if (signedNAV < markedFloor) {
       diff = markedFloor - signedNAV
       divergenceBps = diff * 10_000 / markedFloor
       if (divergenceBps > NAV_DIVERGENCE_THRESHOLD_BPS) {
           consecutiveDivergenceBreaches++
           if (consecutiveDivergenceBreaches >= 2) {
               emit NavDivergenceObserved(strategy, signedNAV,
                                           markedFloor,
                                           snapshotNonce=lastNAVTimestamp)
           }
           // counter is monotonic until reset below
       } else {
           consecutiveDivergenceBreaches = 0
       }
   } else {
       // signedNAV ≥ cashHeld is consistent with NAV ≥ cashHeld.
       consecutiveDivergenceBreaches = 0
   }
   ```

4. **No `queueSlash`.** `StrategyRegistry` is immutable in Phase 3 —
   adding the helper requires a full redeploy + re-registration of
   every strategy, the same blocker we hit on WS-CX-1's
   `payDefundReward`. v1 ships event-only: the multi-sig watches
   `NavDivergenceObserved` off-chain (Goldsky → ops alert) and calls
   the existing `StrategyRegistry.slash(strategyId, amount,
   "NAV_DIVERGENCE")`. Documented as a v1 deviation in
   `Helios.md §6.4` + §17 Phase 1 (alongside `payDefundReward`).

5. **No oracle-stale gate.** The cash-floor check reads
   `baseAsset.balanceOf(this)` — no oracle dependency. The §6.3
   defund path keeps its own freshness gate.

6. **Tests** (`contracts/test/StrategyVault.t.sol`, append a
   `── reportNAV NAV-divergence` block):

   - Single below-floor breach → counter = 1, no event.
   - Two consecutive below-floor breaches → counter = 2,
     `NavDivergenceObserved` emitted with the right `(signed,
     marked, snapshotNonce)` triple.
   - Breach → recover (`signedNAV ≥ cashHeld`) → breach: counter
     resets between, no event on the third report.
   - Three+ consecutive breaches: counter increments past 2 (no
     re-emission needed at each step — a single emission per
     2-consecutive episode is enough; we keep emitting to allow
     off-chain debouncing).
   - Below floor by < 5% (e.g., 200 bps) → counter not incremented.
   - Owner setter: `setNavDivergenceThresholdBps` rotates the
     parameter; non-owner reverts.

7. ABI regen + subgraph schema bump for `NavDivergenceObserved`
   (deferred to subgraph deploy in WS-SVC-1 along with the
   `DefundObserved/Armed/Cancelled/Finalized` events).

---

### 4.3 WS-SVC-1 — Sentinel observes chain events

**Why.** `TODO.md` line 396 — `services/sentinel` only emits its own
decision-loop events to the WS feed. During an
`scripts/e2e-scenario.sh` run that drives `AllocatorVault` directly,
the dashboard activity rail stays blank. The auto-defund signature
moment renders nothing because the event source is Sentinel and the
chain is doing the work.

**Implementation.**

1. **Chain-watcher module** (`services/sentinel/src/sentinel/chain_watch.py`):
   - Polls `eth_getLogs` on a fixed cadence (1s during scenario,
     5s steady-state) against Kite RPC, scoped to addresses read
     from `contracts/deployments/kite-testnet.json`.
   - Watched events: `AllocationCreated`, `AllocationIncreased`,
     `StrategyDefunded`, `DefundTriggered`, `DefundFinalized`,
     `NAVReported`, `NavDivergenceObserved`, `Reallocated`.
   - For each new log, builds a `SentinelEvent` of the existing
     shape (see `services/sentinel/src/sentinel/events.py`) and
     pushes it to the WS broadcast channel.
   - Uses `eth_blockNumber` checkpoint persisted to disk so a
     restart doesn't replay history.
2. **Dedup vs decision-loop events.** Both Sentinel's own decision
   loop and the chain watcher will see the same on-chain
   confirmation. Dedup key = `(tx_hash, log_index)`; decision-loop
   events are tagged `source="decision"`, chain events tagged
   `source="chain"`. The WS feed prefers `chain` (truth) when both
   land within 30s; if only `decision` arrived (chain unhealthy)
   it stays.
3. **Tests** (`services/sentinel/tests/test_chain_watch.py`):
   - Anvil fixture that fires `AllocationCreated` → WS receives
     `SentinelEvent(kind="allocation_created", ...)` within 2s.
   - Restart with checkpoint → no replayed events.
   - Dedup: decision-loop emit + chain emit for the same tx →
     single event on the WS feed, source=`chain`.
4. **Acceptance.** During `scripts/e2e-scenario.sh`, the dashboard
   `/dashboard` activity rail must print the Phase 1 sequence
   verbatim — `AllocationCreated`, `StrategyDefunded`, `NAVReported`.
   Closes the local-testing Tier 3 caveat.

---

### 4.4 WS-FE-1 — Passport onboarding rebuild

**Migrates every `[PASSPORT-STUB]` tag.** Affected files:

- `frontend/src/components/onboard/OnboardClient.tsx` (lines 6, 80, 176)
- `frontend/src/lib/sentinel.ts` (line 116)
- `frontend/src/components/dashboard/WithdrawControl.tsx` (line 5)

**Steps.**

1. **Dependencies.** `frontend/package.json`:
   - `@gokite-network/auth@0.1.16` (pin exact)
   - `gokite-aa-sdk@1.0.15` (pin exact)
   - **Do not** drop wagmi/viem. Operator-facing tools and
     `WalletChip` non-onboarding paths still use plain EOAs in
     dev / e2e (the e2e harness signs with anvil keys, not
     Passport).
2. **Env vars** (`/.env.example` + `frontend/.env.example`):
   - Remove `KITE_PASSPORT_SIGNER_PK` (was a stub left over from
     v0 spec; never read by frontend).
   - Add `NEXT_PUBLIC_PARTICLE_PROJECT_ID`,
     `NEXT_PUBLIC_PARTICLE_CLIENT_KEY`,
     `NEXT_PUBLIC_PARTICLE_APP_ID`,
     `NEXT_PUBLIC_AA_ENTRYPOINT_ADDRESS`,
     `NEXT_PUBLIC_AA_FACTORY_ADDRESS`.
   - Pull EntryPoint + factory from Kite docs (per
     `docs/kite-passport-notes.md` §"Versions"); document the
     2026-04-30 spike values in `docs/kite-passport-notes.md`
     §"Versions" with a "verified Phase 4" tag.
3. **Provider tree** (`frontend/src/app/providers.tsx`):
   - Add a `<PassportProvider>` wrapping `WagmiProvider` (do not
     replace it). Initializes `GokiteNetwork` + `SmartAccount`
     once at mount.
   - Expose `usePassport()` hook returning `{ login, logout,
     aaAddress, sdk, signFn }`.
4. **`OnboardClient.tsx`** rewrite per `kite-passport-notes.md`
   Pattern 1:
   - Replace MetaMask `useAccount()` + `useSignMessage()` with
     `usePassport()`.
   - Drop the `signature` field from `MetaStrategyPayload` for
     Passport-onboarded users. The userOp signature is verified
     at the EntryPoint; on-chain authorization is `msg.sender ==
     owner` on `UserVault`. Keep the legacy EIP-191 path for
     dev/e2e (anvil signers) under a `process.env.NEXT_PUBLIC_USE_PASSPORT`
     flag, default true in prod, false when `KITE_RPC_URL` points
     at anvil.
   - Build the four-call batched userOp:
     `USDC.approve(UserVault, deposit) →
      UserVault.deposit(deposit) →
      UserVault.setMetaStrategy(metaStruct) →
      UserVault.delegateToAllocator(SENTINEL_EOA)`.
   - Estimate via `sdk.estimateUserOperation` so the UI can show
     "paymaster: sponsored" when available; fall back to USDC
     payment via `sendUserOperationWithPayment` per Pattern 1.
   - Submit via `sendUserOperationAndWait`. **Single passkey
     prompt** for the whole flow.
5. **`sentinel.ts`** drops the `[PASSPORT-STUB]` comment; the
   service-side payload shape stays the same so the Sentinel API
   needs no change. (The signature field becomes `"0x"` for
   Passport-onboarded payloads, distinguished by a new
   `auth: "passport" | "eip191"` enum.)
6. **`WithdrawControl.tsx`**: withdrawals also flow through the
   AA wallet — `UserVault.withdraw(amount)` is a single userOp.
   Drop the stub comment.
7. **Acceptance** (in addition to TODO.md line 415):
   - Zero `[PASSPORT-STUB]` tags remain in `frontend/src/`.
   - `pnpm --filter frontend test` (component tests) green.
   - Manual dev-loop: `pnpm dev` → connect with Passport widget →
     onboard with $100 → dashboard renders correct AA address +
     deposit landed in UserVault.
   - `scripts/e2e-scenario.sh` continues to pass against the EIP-191
     dev path (e2e doesn't need Passport, anvil signers are fine).

**Open questions** (resolve early in WS-FE-1, before lift-off):

- Does `@gokite-network/auth@0.1.16` work with React 18 / Next 14
  App Router server components? Spike on day 1 — if SSR breaks,
  wrap the provider in a `dynamic(... { ssr: false })` boundary
  the same way `WalletChip` does today.
- Does `gokite-aa-sdk@1.0.15` accept anvil RPCs for local dev?
  If not, the dev path stays on EIP-191 indefinitely — that's fine,
  Pattern 1 ships only against testnet.

---

### 4.5 WS-FE-5 — Sunburst v1

**Scope per `DESIGN.md §11`.** Concentric-ring viz, two layers
(user → allocator → strategies). Positions ring deferred to v2;
bespoke d3 + ticked-motion physics deferred. v1 ships layout, color,
hover, click-through, and a coarse step-resize on rebalance — not
full ticked motion.

**Implementation.**

1. **Component** (`frontend/src/components/sunburst/`):
   - `Sunburst.tsx` — props `{ user, allocator, strategies[] }`.
     Hand-rolled SVG. Two rings; segments sized by capital weight;
     fill = chain-color from `--chain-{kite,base,arbitrum}` tokens;
     stroke = `--surface-line`.
   - `useSunburstLayout.ts` — pure function that maps
     `{ allocator, strategies }` to arc paths via `d3-shape`'s
     `arc()` (we already vendor d3-shape via Recharts).
   - `MiniSunburst.tsx` — same component clipped to 64×64 for
     allocator cards on `/allocators`.
2. **Selected-state**: amber accent on the segment matching the
   currently-focused strategy. Click navigates to
   `/strategies/[id]`. Hover surfaces a tooltip with name,
   allocated, current NAV, P&L.
3. **Motion (v1).** No ticked motion library. On capital weight
   change, segments animate through 4 discrete steps over 320ms
   via CSS `transition` on `d` attribute set to `step-end`-ish
   curve. (Real ticked motion physics is roadmap.)
4. **Reduced-motion**: respects the WS-FE-7 `prefers-reduced-motion`
   media query — animations become instant.
5. **Storybook stories** (`frontend/src/components/sunburst/Sunburst.stories.tsx`)
   covering: 3-strategy / 5-strategy / single-allocator / cascade
   in-progress / defund-rebalance.
6. **Performance gate.** 60fps at 5 segments on a typical laptop.
   Verified by Playwright frame-counting against the cascade
   storybook (same harness as Phase 1 perf).
7. **Tests**:
   - Snapshot tests for layouts at the five canonical states.
   - Click navigates to the right route (Playwright + storybook).
   - `useSunburstLayout` arc geometry math is unit-tested
     (Vitest).

**Where it lands.**

- `/dashboard` primary chart slot above the allocations table
  (replaces today's nothing).
- `/strategies/[id]` Allocators panel surfaces a mini-sunburst
  per allocator's allocations to that strategy.
- `/allocators` list page already has `AllocatorCard`; embed
  `MiniSunburst` in the card.

---

### 4.6 WS-FE-3 — `/strategies/[id]`

**Per `DESIGN.md §9.5`.** Self-contained data sheet. Implemented
under `frontend/src/app/strategies/[id]/page.tsx` (new) +
`frontend/src/components/strategies/detail/`.

**Sections in render order:**

1. **Manifest header.** Name, class, operator, chain badge,
   registered date, stake (in USDC), fee rate, capacity (used
   vs max), asset universe rendered as chips. Pulls from
   `StrategyRegistry` + `StrategyVault.manifest()`.
2. **Reputation breakdown panel.** Reuses
   `frontend/src/components/audit/ComponentBreakdown.tsx` (Phase 2
   shipped) with five components (perf/risk/proof/stake/age)
   sourced from `services/reputation`'s `/v1/audit/{actor}` endpoint.
3. **P&L curve.** Recharts `LineChart` + shaded `Area` for
   drawdown envelope. Cumulative P&L (USDC) over time,
   1-snapshot resolution. Drawdown envelope = (HWM − NAV) /
   HWM, shaded under the line.
4. **Recent trades table.** Last 20 `Trade` rows from subgraph.
   Columns: timestamp, direction, asset_in, asset_out, size,
   slippage, proof status (shield icon, clickable opens
   audit modal), tx hash → Kitescan deeplink.
5. **Current allocators panel.** Mini-sunburst per allocator
   (capital from each), table beneath: allocator name, capital
   deployed, since-when, current NAV.
6. **`paramsHash` rotation history.** Closes
   `TODO.md` line 276. Pulls from subgraph
   `ParamsRotation` entity (Phase 2 schema). Rendered as a small
   timeline at the bottom of the manifest.
7. **NAV timeline.** Secondary chart, 1-min resolution, last 24h
   default. Toggle 24h / 7d / 30d.

**Subgraph queries.** Add
`fetchStrategyDetail(strategyId)` to `frontend/src/lib/goldsky.ts`
covering manifest + recent trades + allocators + paramsHash
history in a single GraphQL query (use `@derivedFrom` joins).

**Tests.**

- Row click from `/strategies` lands on the right detail page
  (Playwright).
- All six sections render against a fixture subgraph payload.
- Empty states (no trades, no allocators, no NAV history) render
  without throwing.

---

### 4.7 WS-FE-4 — `/audit/[strategy]`

**Per `DESIGN.md §9.7` + §12 ("Celebrated").**

**Existing `/audit/[actor]/page.tsx`** is the reputation-engine
audit (Phase 2) and stays unchanged. The Phase 4 page adds
`/audit/[strategy]/` (separate route segment) — a forensic
**per-strategy trade list** with celebrated ZK treatment.

**Sections:**

1. **Header.** "Audit · MomentumKite-A" — name, class, operator,
   stake. Three quick links: GitHub source, Kitescan address,
   download-all-data JSON.
2. **Every trade ever, paginated.** 50 rows per page. Columns:
   timestamp (UTC ISO), tx hash, proof hash, verification result
   (large shield treatment — green / outline / red), trade
   details. Click on any row expands inline to show full proof
   public-input vector + calldata hex.
3. **"Verify this proof yourself" CTA.** Opens a modal:
   - Copyable command block:
     `node scripts/verify-trade.js --tx 0xabc... --rpc $KITE_RPC`
   - Explanation of what `verify-trade.js` does: re-runs Groth16
     on the public-input vector against the on-chain verifier;
     prints the verifier's exact return.
   - Link to `scripts/verify-trade.js` source on GitHub.
   - **Note:** `scripts/verify-trade.js` is a Phase 6 polish
     deliverable per `TODO.md` line 473. For Phase 4, the modal
     documents the command shape and links to a placeholder
     script that prints "verify-trade.js — full implementation
     lands Phase 6 polish". The command block itself is real and
     copyable; only the binary it invokes is stubbed. (Avoids
     stranding the audit page until Phase 6 polish.)
4. **Reputation calculation inputs panel.** Re-uses
   `ComponentBreakdown` from `/audit/[actor]`. Shows the inputs
   (realized P&L, drawdown events, proof validity rate) that
   produced the current reputation score.
5. **JSON dump link.** `/api/audit/{strategy}/dump` returns a
   sane JSON ToC (manifest + every trade + every NAV report +
   every paramsHash rotation + every reputation update). Backed
   by a single Goldsky query.

**ZK treatment** (DESIGN §12 "celebrated"):

- Shield icons are 32×32 here vs 16×16 elsewhere.
- Each row has a "verified by Groth16" caption.
- Proof hash is monospace, full-length (no truncation).
- The "verify yourself" CTA is amber-accented (one of the few
  places amber appears outside selected/active state).

**Tests.**

- Audit page renders with 100 trade rows fixture, paginates.
- "Verify yourself" modal opens, command block is copyable.
- JSON dump returns >0 bytes against the e2e fixture.

---

### 4.8 WS-FE-2 — `/` landing + `/judge`

**`/` landing per `DESIGN.md §9.1`.** Replaces the Phase 0
TokenSwatch placeholder (`frontend/src/app/page.tsx`).

- Headline: **"A capital market for AI strategies. ZK-attested."**
  (Or similar — final copy is a designer-review item; the spec
  lists "confident headline that states the thesis" without
  prescribing words. Draft three variants for review.)
- Live stats band — total capital managed, active strategies,
  attested trades, active allocators — pulled from subgraph
  via `fetchLandingStats()` (new in `goldsky.ts`). Numbers in
  monospace, large, no decoration. Refresh on a 30s cadence.
- Two primary CTAs: "Enter app" → `/dashboard` (or `/onboard`
  if no AA wallet), "Read the spec" → `/judge`.
- Secondary links row: GitHub, docs (operator-guide on
  GitHub), demo video, judge eval. No feature sections, no
  testimonials, no FAQ.
- One-screen on desktop; one-tall-scroll on mobile.

**`/judge` per `DESIGN.md §9.8` + `TODO.md` line 371.**

- Top: 3-min demo video iframe + "90s backup" link. Both Vimeo
  hosted (link is fine as a placeholder until Phase 6 polish demo
  recording lands).
- "Try the demo scenario" button — POST `/v1/scenario/run` on
  Sentinel; the dashboard streams the cascade. Button is the
  one amber accent on the page.
- Contract addresses table (Kite testnet today, Base/Arbitrum
  sepolia rows reserved as "Phase 5"; the Kite mainnet row is
  marked "Stretch — only if mainnet promotion is exercised").
  Each row links to Kitescan / BaseScan / Arbiscan. **Reads from
  `contracts/deployments/*.json` at build time** so addresses
  don't drift.
- GitHub links: code, SDK packages (4), circuits, subgraph.
- `verify-trade.js` command block, syntax-highlighted via
  Shiki (already in deps via `@shikijs/markdown`). Same Phase 6
  polish caveat as §4.7.
- 5-step eval checklist from `Helios.md §19`, each step a
  direct link.
- Live transaction counts, refresh on 30s — strategies deployed,
  attested trades, defund events, cross-chain messages, total
  capital cycled. Pull from subgraph.
- **Self-sufficient even without VPS up** (`TODO.md` line 371):
  expose Kite testnet RPC URL, all addresses, Goldsky endpoint,
  and Kitescan deeplinks for one canonical demo scenario's
  `TradeAttested` / `Reallocated` / `AutoDefunded` events. The
  goal: a judge with no VPS access can hit Kitescan + Goldsky
  directly and verify the system end-to-end. Hard-code the txs
  for "the canonical Phase 1 scenario run" at build time
  (script `scripts/snapshot-judge-fixtures.ts` writes
  `frontend/src/lib/judge-fixtures.json`).

**Routes.** New file `frontend/src/app/judge/page.tsx`. Top nav
gains a `/judge` link in `TopNav.tsx` (replace the `/onboard`
hotkey hint with a `g j` chord pointing to `/judge`).

---

### 4.9 WS-FE-6 — Signature interactions

The headline. Three motion budgets per `DESIGN.md §13`. Lands
**after** WS-CX-1/2 + WS-SVC-1 + WS-FE-5 + the static surfaces.

**Cascade (DESIGN §10.1):**

- Trigger: WS event `metaStrategyAccepted` (Sentinel emits this
  on `/v1/onboard` POST success).
- Sequence:
  1. `/dashboard` chrome renders empty (allocations table headers
     only, sunburst at zero).
  2. T+0 — top strip "$1,000 deposited" (single discrete render).
  3. T+0–80ms — sunburst grows from center outward. Inner ring
     (allocator) fills first as a single segment. Animation is
     a 4-step `step-end` interpolation over 320ms (motion
     budget — sunburst rotation per §13 exception list).
  4. T+200ms onward — strategy allocations appear as on-chain
     `AllocationCreated` events arrive. Each row prints with
     **80–120ms stagger** (the actual receipts' timestamps drive
     the stagger; we don't add fake delay). Each row appears
     instantly within the stagger.
  5. Activity rail prints each event as it lands (Sentinel chain
     watcher → WS).
- **Source of truth.** Every visible step maps to an actual
  on-chain receipt via WS-SVC-1's chain watcher. No simulated
  delay. The cascade *is* the chain confirming.

**Auto-defund (DESIGN §10.2):**

- Trigger: WS event `defund_finalized` (Sentinel chain watcher
  → `DefundFinalized` log).
- Sequence (~5–6s):
  1. T+0 — strategy row's drawdown indicator ticks through
     amber to red (discrete tick; CSS `transition: none`).
  2. T+0 — red 2px left-border on the row (instant).
  3. T+100ms — activity rail prints "MomentumKite-A defunded.
     Drawdown threshold breached at -15.2%".
  4. T+0 → T+2000ms — allocated capital column ticks down to
     zero in monospace digit-stepping (30ms per digit step
     per `DESIGN §13`).
  5. T+0 → T+320ms (overlapping) — sunburst segment shrinks via
     4-step step-end; remaining segments rebalance.
  6. T+~3000ms (when Sentinel fires the replacement allocation)
     — new row appears in the allocations table, sunburst grows
     a new segment, rail prints "Capital reallocated to
     MeanRevArb-E ($300)".
  7. T+~5000ms — all events committed.
- **Thermostat feel.** No alarm sound. No flash. No shake. The
  red border is the strongest signal; it turns off when the
  replacement lands. WCAG: red is paired with the negative-sign
  on the drawdown number.

**Cross-chain reputation update (DESIGN §10.3):**

- Trigger: WS event `reputation_updated` from the reputation
  engine, with `source_chain != current_chain`.
- Sequence:
  1. Strategy's chain badge pulses **once** (`@keyframes`,
     1×600ms).
  2. Reputation column shows a small "in flight" indicator
     (clock icon, `--fg-muted`).
  3. T+30–60s (LayerZero latency) — when the destination-chain
     `ReputationUpdated` lands, indicator resolves and the
     score ticks to its new value via digit-stepping.
- **Phase 4 lands the visual machinery, not the cross-chain
  source.** Phase 5 wires LayerZero. Until Phase 5, the
  reputation engine emits `reputation_updated` synchronously;
  the cross-chain visual is dormant. Test fixture
  `scripts/scenario-cross-chain-rep.ts` posts a synthetic
  `reputation_updated` with `source_chain="arbitrum"` to
  exercise the visual without LayerZero.

**Tests.**

- Playwright signature-interaction tests
  (`frontend/tests/playwright/signatures.spec.ts`):
  - Cascade: 4 staggered rows render within 80–120ms each;
    sunburst segments fill in expected order.
  - Auto-defund: red border + digit-step + sunburst step + rail
    print all happen within their nominal windows.
  - Cross-chain pulse: chain badge pulse fires once,
    `aria-live` announces the in-flight state.
- Reduced-motion: all three reduce to instant (verified by
  Playwright with `prefers-reduced-motion: reduce`).

---

### 4.10 WS-FE-7 — Polish

Cross-cutting items from `TODO.md` lines 388–397. Each is a small
PR; bundle when sensible.

1. **Defund bond UX** (`TODO.md` line 389). Activity rail prints
   "Defund pending confirmation — $250 reward locked" when
   `DefundTriggered` lands. Confirmation window countdown shown
   inline. On `DefundFinalized`, prints reward paid + bond
   refunded. `CustomizationPanel.tsx::DefundDefaults` swaps from
   read-only to editable: `defundTwapBars` (slider 1–24, default
   3), `defundBondBps` (10–500 bps, default 50),
   `defundConfirmBlocks` (1–60 blocks, default per
   MetaStrategyLib). Inline help-text per field.
2. **Keyboard nav** (`DESIGN §5.5`). Already partial — `g d`,
   `g s`, `g a`, `g o`, `?`. Add: `j` / `k` for table row
   nav (every table — strategies, allocations, audit), `/` for
   search focus on `/strategies`, `Esc` for modal dismiss,
   `g j` for `/judge`. Discoverable via `?` panel —
   regenerate the panel content from `useHotkeys` registry.
3. **Reduced-motion media query**. All signature interactions
   reduce to instant via a single CSS variable token
   `--motion-scale: 0` under `@media (prefers-reduced-motion: reduce)`.
   Audit every `transition`, `animation`, `@keyframes` to use the
   token.
4. **Focus rings** (`DESIGN §14.3`). Every focusable element
   gets a 1px amber outline with 2px offset (`focus-visible`).
   Replace any `outline: none` left from Phase 1.
5. **WCAG AA audit**. Run axe-core via Playwright across all
   surfaces; remediate every fail. Bake into CI as a smoke test.
6. **Projector legibility check** (`DESIGN §14.5`). Manually
   load on a 1920×1080 projector at low contrast. Capture
   screenshots; iterate on any column that crushes.
7. **`/onboard` error UX** (`TODO.md` line 395). Distinguish
   "signed but allocator unreachable" (retryable, signature
   kept) from "signing failed" (rejected/aborted) in
   `OnboardClient.tsx:72-74`. Surface raw `Failed to fetch`
   only as a technical detail toggle; primary error message is
   user-facing.
8. **Tabular-nums everywhere**. Audit every numeric column:
   it must use `tabular-nums` on the parent (`Numeric` atom
   already has this; some inline numbers in the activity rail
   don't). Closes a perf-related layout-shift cause per
   `DESIGN §14.5`.

---

### 4.11 WS-ACC — Acceptance

The closer.

1. **Phase 1 scenario re-runs at full visual fidelity** (TODO
   line 413). `scripts/e2e-scenario.sh` runs against a fresh
   stack; record the dashboard with Playwright video; manual
   review confirms cascade staggers and auto-defund lands as
   thermostat moment.
2. **Lighthouse re-gate** (`DESIGN §14.5`). `/dashboard` perf
   ≥ 85, LCP < 2s, CLS = 0. Re-measure with the sunburst loaded
   — if it regresses past the budget, lazy-load the sunburst
   on intersection (per the Phase 1 WS5 measurement note).
3. **Designer review checklist** (TODO line 414):
   - "Bloomberg meets Vercel v0" — landing/onboard calm,
     dashboard/strategies dense.
   - Amber budget (2–5%) respected on every page.
   - No purple gradients, no glassmorphism, no neon glows.
   - All numerics tabular.
   - Motion budget — no smooth transitions outside the §13
     exception list.
4. **No `[PASSPORT-STUB]` tags remain** (TODO line 415).
   `git grep PASSPORT-STUB frontend/src` returns zero.
5. **Cross-cutting gates** (TODO lines 514–522): coverage ≥
   85% on every contract, ABI types regenerated, every
   numeric class has its full pipeline, no `any` in TS, no
   unformatted Solidity, no unlinted Python.

**Release.** Tag `v0.4.0` on `main` once all five gates green.
Update `CLAUDE.md` "Current phase" + `TODO.md` Phase 4 status
line.

---

## 5. Schema, ABI, and address bookkeeping

- **ABI bump.** WS-CX-1 + WS-CX-2 add events and one helper
  function (`StrategyRegistry.queueSlash`). Regenerate
  `packages/contracts-abi/`; downstream services (sentinel,
  reputation), the subgraph, and the frontend pick up via
  workspace deps. Confirm `pnpm --filter contracts-abi build` +
  the dependent builds (`pnpm build`, `uv run python -m
  services.sentinel`) all green before opening the WS-CX PRs.
- **Subgraph schema bump (v0.2.x).** New entities/fields:
  `DefundTrigger`, `DefundFinalized`, `NavDivergence`. Do **not**
  bump `graph-cli` past 0.83.0 / `graph-ts` past 0.31.0 / apiVersion
  past 0.0.7 (memory: Goldsky on Kite testnet rejects WASM 0xFC).
  Deploy as `helios/v0.2.0`.
- **Deployments.** No new contract addresses on the WS-CX path —
  upgrade the existing AllocatorVault and StrategyVault impl via
  UUPS. **Six** StrategyVault proxies are upgrade-eligible (the V2
  + V3 set on Phase-3 impl `0x4510eA78…`); the **base trio** stays
  on the legacy impl per the storage-layout split documented in
  `CLAUDE.md` "Key addresses" (`a4b844a` mid-struct change). Phase
  4 e2e + signature-moment demos run against V2/V3 only.
  AllocatorVault is single-impl, upgrade applies cleanly. New
  addresses written to `contracts/deployments/kite-testnet.json`
  by the deploy script; frontend reads from the JSON, no hardcoded
  addresses.

---

## 6. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Particle Network widget breaks against Next 14 SSR | M | Day-1 spike in WS-FE-1; fall back to `dynamic({ ssr: false })` boundary |
| `OraclePriceAnchor.twapBars(N)` not exposed; TWAP loop must be on-chain in AllocatorVault | M | Verify against deployed `0x566e1f1b…`; if absent, add `twapBars()` view on the anchor (read-only, no upgrade gating). Pre-WS-CX-1 work |
| Sunburst hand-rolled SVG hits 60fps regression | L | Storybook `useFrameCounter` harness checks; if fail, lazy-load sunburst on dashboard mount |
| Sentinel chain-watcher polling CPU cost on dev VPS | L | 5s steady-state cadence; switch to 1s only during scenario; checkpoint to disk so restart doesn't replay |
| Auto-defund bond economic griefing (operator-funded triggers) | M | Bond cap at `defundRewardCapUsd`; reward sourced from allocator `_accruedFees` (v1 deviation, see §4.1); v2 path = stake-based reward via registry rebuild |
| Lighthouse regression from sunburst | M | Lazy-load sunburst on dashboard intersection; pre-warm via Phase 1 WS5 pattern |
| Passport AA SDK requires testnet not anvil | L | Keep wagmi/EOA path under `NEXT_PUBLIC_USE_PASSPORT` flag for dev/e2e |

---

## 7. Out of scope (explicitly deferred)

Per `TODO.md` Deferred § lines 526–537:

- **Bespoke d3 sunburst with mechanical step animation.** v1 is
  hand-rolled SVG. Roadmap: post-hackathon Phase 1.
- **`/docs` embedded operator+allocator guides.** `/judge`
  links out to GitHub markdown.
- **`/allocators` side-by-side compare.** Per-allocator detail +
  list page already shipped (Phase 3).
- **Telegram bot.** Activity rail covers the demo; bot post-hack.
- **x402 paid services.** Not on the headline 3-min script.
- **Helix regime/correlation.** Allocator-SDK exposes hooks;
  Helix v1 doesn't use them.

These remain in the spec as v2 directions; do not regress them
into Phase 4.

---

## 8. Done definition

Phase 4 is done when **all of the following** are true:

- `TODO.md` Phase 4 acceptance checklist (lines 411–415) all checked.
- `forge test -vv && forge coverage` clean, ≥85% line coverage on
  every contract.
- `pnpm --filter frontend build && pnpm --filter frontend test &&
   pnpm --filter frontend test:e2e` clean.
- `scripts/e2e-scenario.sh` green against a fresh `pnpm dev` stack.
- Lighthouse `/dashboard` ≥ 85 perf, LCP < 2s, CLS = 0.
- Zero `[PASSPORT-STUB]` tags in `frontend/src/`.
- Manual designer-review pass.
- `v0.4.0` tagged on `main`.
- `CLAUDE.md` "Current phase" updated to **Phase 5 — Cross-chain**.
