# Helios — Demo script (v1 submission, 4 min pre-recorded)

> **Format.** Pre-recorded screencast assembled from independent
> takes. Every on-chain artifact in the demo is real. Per
> `Helios.md §14.2`, the scenario-mode segment used for the
> auto-defund beat is explicitly carved out — the mechanism,
> transactions, and proofs are real; only the price feed driving the
> NAV trajectory is replayed.
>
> **Total runtime.** 4:00 exact. 235s of body + 5s closing card.
>
> **Average pace.** ~113 wpm over the full body, leaving comfortable
> headroom for pauses and on-screen action between voiceover lines.

---

## Stopwatch

| # | Beat | In | Out | Length |
|---|---|---|---|---|
| 0 | Preamble — the problem | 0:00 | 0:35 | 35s |
| 1 | One-passkey onboarding | 0:35 | 1:15 | 40s |
| 2 | Autonomous multi-chain allocation | 1:15 | 2:10 | 55s |
| 3 | The ZK guarantee | 2:10 | 2:55 | 45s |
| 4 | Cross-chain reputation | 2:55 | 3:25 | 30s |
| 5 | Auto-defund (headline) | 3:25 | 3:55 | 30s |
| 6 | Closing card | 3:55 | 4:00 | 5s |

---

## Beat 0 — Preamble (0:00–0:35, 35s)

**On-screen.**
- Open on the Vercel landing page; the live `LandingStatsBand`
  should be visible (strategies-online + total-NAV ticker).
- 0:05 — fade in title card overlay: *"AI agents are running real
  capital. Today's choice: trust them, or babysit them."*
- 0:15 — cross-fade to second title card: *"Helios is a third
  option."*
- 0:23 — fade out title cards; hold on the landing page until 0:35.

**Voiceover (75 words, ~129 wpm).**

> *"AI trading agents are managing real capital today. Users get
> two bad options: trust an opaque pool, or babysit a strategy
> yourself. Helios is a programmatic capital market where AI
> agents compete for user capital. Every trade carries a
> zero-knowledge proof binding it to the strategy's declared
> class. Reputation accrues from realized, attested performance.
> The user signs once. The protocol enforces everything else."*

**Capture.** Single take of the landing page in a non-incognito,
fully-hydrated session. Warm the dev server with one `curl /` before
the take so the page TBT is at steady state. Title overlays added
in post.

---

## Beat 1 — One-passkey onboarding (0:35–1:15, 40s)

**On-screen.**
1. `/onboard` opens with template chooser.
2. Click **Balanced**.
3. Sentinel allocator pre-selected with "Official Reference" badge.
4. Click **Approve**.
5. Passkey / biometric prompt → tap to confirm.
6. Spinner → "Welcome" lands on `/dashboard`.
7. Cut to Kitescan tab: the userOp's four inner calls visible —
   `USDC.approve` + `UserVault.deposit` + `setMetaStrategy` +
   `delegateToAllocator`.

**Voiceover (60 words, ~90 wpm — slow to match on-screen action).**

> *"One passkey. One transaction. The user picks a meta-strategy
> template, delegates to Sentinel — the reference allocator —
> and the userOp executes four on-chain calls atomically. The
> wallet is account-abstracted, the keys are MPC-backed by Kite
> Passport, and the gas is sponsored. From here, the user is
> done. The protocol acts within bounds they set."*

**Capture notes.**
- Fresh browser profile so Passport runs from zero state. Clear
  localStorage + sessionStorage if a take fails.
- Pre-fund the deployer EOA with KITE for paymaster sponsorship.
- Frontend env must have `NEXT_PUBLIC_USE_PASSPORT=1` and a
  populated `NEXT_PUBLIC_PARTICLE_*` set + Kite AA addresses.
- If a take fails mid-userOp, rotate to a brand-new browser profile
  — do **not** reuse an in-progress one (AA-salt cache fragility).

---

## Beat 2 — Autonomous multi-chain allocation (1:15–2:10, 55s)

**On-screen.**
1. `/strategies` directory: 12 rows visible — 9 Kite + 2 Base
   (mom.base + mr.base) + 1 Arb (yr.arb). Each row shows class chip
   + chain badge + reputation score.
2. Scroll-tease one Kite row, one Base row, one Arb row to make the
   class × chain matrix legible.
3. Cut to `/dashboard`. The activity rail (streaming from the
   Sentinel WebSocket) prints entries as Sentinel ticks:
   - `ALLOCATION` — Kite-local allocates
   - `REMOTE_ALLOCATION_SENT` — Base + Arb hops
4. Picture-in-picture: Kitescan tab showing the AllocatorVault tx
   fan — same-chain `allocateToStrategy` calls + one batched
   `allocateToRemoteStrategyBatch` cross-chain send.
5. LZScan tab: in-flight → delivered status on the Base + Arb hops;
   destination StrategyVault balance increment visible.

**Voiceover (85 words, ~93 wpm).**

> *"Sentinel ranks all twelve strategies — three classes across
> three chains — by realized performance and stake. It splits the
> deposit across the top candidates. Kite-local allocates land
> directly. Cross-chain allocates ride LayerZero V2 — to Base for
> spot pairs against deep liquidity on Uniswap, to Arbitrum for
> yield on Aave. Same-destination strategies batch into one
> message to cut cost. The user never picks a chain. They picked a
> meta-strategy. The allocator does the rest."*

**Capture notes.**
- Stage a fresh deposit large enough to clear the Tier-1 threshold
  gate ($10 / strategy) so cross-chain submits actually fire.
- Sentinel allocator EOA must hold ≥ 3.5 KITE before the take
  (~1.08 KITE per LZ V2 hop on testnet).
- Canonical fallback material if a fresh take doesn't land: the
  three verified hops from 2026-05-14
  (`docs/Helios v1 acceptance.md §2.2`):
  - mr.base — tx `0x6ef584a1…` (Kite block 21392016)
  - mom.base — tx `0xfee792dc…` (Kite block 21392017)
  - yr.arb — tx `0xcda2e6bd…` (Kite block 21392018)

---

## Beat 3 — The ZK guarantee (2:10–2:55, 45s)

**On-screen.**
1. Goldsky GraphQL playground (`helios/v0.9.0`) with this query:
   ```graphql
   {
     tradeAttesteds(
       where: { strategyVault: "0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a" }
       orderBy: blockNumber
       orderDirection: desc
       first: 8
     ) {
       id
       blockNumber
       transactionHash
       declaredClass
       publicInputs
     }
   }
   ```
2. Result list: 8+ real `TradeAttested` events from mr.kite
   (`phase6VaultMeanReversion`), oldest from 2026-05-12.
3. Click one — expand to show the public-input array:
   `oracle_root`, `params_hash`, `asset_universe_hash`,
   `action_kind = ENTRY`, `declared_class = mean_reversion_v1`,
   `decimals_in` / `decimals_out`.
4. Switch to `/judge` page → scroll to the "Verify a trade
   yourself" command block.
5. Open a terminal in a second window. The command is pre-typed:
   ```bash
   node scripts/verify-trade.js <tx-hash>
   ```
6. Paste the tx hash from step 2 → run.
7. Terminal output streams: fetched receipt, decoded proof, ran
   Groth16 verifier, exit code 0 → `PROOF VALID ✓`.

**Voiceover (90 words, ~120 wpm).**

> *"Every trade carries a Groth16 zero-knowledge proof binding it
> to the strategy's declared class. The mean-reversion agent here
> literally cannot execute a momentum entry — the on-chain
> verifier rejects the transaction before it lands. Eight
> thousand circuit constraints enforce the class invariants. We
> ship a CLI that anyone can run: it pulls the trade off-chain,
> decodes the proof from calldata, and re-runs the same verifier
> locally. Forty milliseconds. No trust required. Cryptography
> all the way down."*

**Capture notes.**
- Pre-pick a clean `TradeAttested` tx hash from mr.kite (any from
  2026-05-12+ works). Memory note `project_phase6_ws9_dedicated_keys`
  has the canonical first-eight set.
- Terminal pre-positioned with the command line typed; the
  demonstrator pastes the hash and hits enter on camera.
- Real CLI run, no fakery.

---

## Beat 4 — Cross-chain reputation (2:55–3:25, 30s)

**On-screen.**
1. `/strategies` page, filter to **Base** chain → mom.base +
   mr.base visible with non-zero reputation scores.
2. Click into one → `/audit/strategy/[id]` shows the reputation
   breakdown: PerformanceScore, StakeWeight, AgeScore,
   ConsistencyScore, RiskAdjustedScore (per `Helios.md §8.2`).
3. Cut to Kitescan: `ReputationAnchor V2-bis` (
   `0x2b6c5f36…`) `postCrossChainUpdate` event on Kite. The GUID
   matches a LayerZero message originating on Base.
4. Visual cue: the chain-badge pulse animation on the activity
   rail (`CROSS_CHAIN_REP_UPDATE_INFLIGHT` → `_RESOLVED`).

**Voiceover (55 words, ~110 wpm).**

> *"Reputation lives canonically on Kite, but strategies trade
> where the venue is best. A Base strategy earns its track record
> on Uniswap. LayerZero V2 stitches it across — the same pipe the
> protocol uses for capital, it uses for trust. An update from
> Base lands on Kite as one signed message. Sentinel's next pass
> sees it."*

**Capture notes.**
- Canonical evidence: the WS10 verification hop — Base→Kite GUID
  `0x24fd5344…` moved SR-v3 `currentReputation` 0 → 750 in a
  single hop (memory `project_phase5_ws10_xchain_verified`).
- The Kitescan tx and LZScan trace are historical, already
  on-chain. Use the existing record; do not stage a new one.

---

## Beat 5 — Auto-defund (3:25–3:55, headline beat, 30s)

> **Single curated pre-recorded segment.** Sentinel runs against a
> scripted price replay that drops one vault's NAV through the
> drawdown threshold in compressed time. All resulting transactions
> are real on-chain. Only the price feed is replayed. Spec
> carve-out: `Helios.md §14.2`.

**On-screen.**
1. `/dashboard` top strip: target vault NAV trends downward over
   compressed clock time.
2. Activity rail prints in sequence (real on-chain events, surfaced
   from Goldsky + the Sentinel WebSocket stream):
   - `DEFUND_ARMED` — drawdown threshold approached
   - `DEFUND_TRIGGERED` — threshold breached; on-chain
     `defundStrategy` fires
   - `STRATEGY_DEACTIVATED` — `StrategyRegistry.active` flips false
   - `REMOTE_ALLOCATION_SENT` — capital rerouted to the next-best
     candidate
3. Kitescan picture-in-picture: the actual `slash` +
   `defundStrategy` transactions.

**Voiceover (75 words, ~150 wpm).**

> *"This is the headline. When a strategy's NAV drops below the
> user's drawdown threshold, the defund is permissionless —
> anyone can fire it. Sentinel does in normal operation. If
> Sentinel went offline, the user could. If the user is asleep,
> anyone else can. No party can suppress it. The mechanism is
> on-chain, the proof is in the receipt, and the capital reroutes
> automatically. No human pressed a button — the protocol acts."*

**Capture notes.**
- One-time scenario-mode setup before recording: run Sentinel
  against a scripted price feed that drops the target vault NAV
  below threshold inside ~60s of compressed clock time.
- All resulting transactions are real on-chain against the
  deployed contracts.
- Frame the recording side-by-side: dashboard activity rail on the
  left, Kitescan tx on the right.
- Fallback if scenario harness slips: pull a historical defund
  event (if any) from Kitescan, show the `permissionless`
  modifier in `StrategyVault.sol`, and re-time the voiceover for
  static evidence.

---

## Beat 6 — Closing card (3:55–4:00, 5s)

**On-screen.** Hero shot of the `/judge` page with overlay text
*"Verify everything yourself"* + the deploy URL + GitHub repo URL.

**Voiceover (12 words, ~144 wpm).**

> *"Helios. Programmable capital, cryptographically enforced.
> Live on Kite."*

---

## Capture sequencing

Record beats in this order — most fragile to most deterministic:

1. **Beat 5 (scenario defund)** — longest setup, most failure modes.
   Get it in the can first.
2. **Beat 2 (multi-chain allocation)** — needs a fresh deposit timed
   against the Tier-1 flush window.
3. **Beat 1 (onboarding)** — fresh browser state; deterministic.
4. **Beat 3 (verify-trade)** — fully deterministic; re-takable any
   time.
5. **Beat 4 (cross-chain rep)** — historical evidence; capture cold.
6. **Beat 0 + Beat 6** — pure landing-page screen capture. Last.

---

## Pre-flight checklist

Before opening the screen recorder:

- [ ] VPS sentinel image is current `main`.
- [ ] Vercel frontend is on latest `main`.
- [ ] `NEXT_PUBLIC_USE_PASSPORT=1` and Particle / Kite AA env vars
      are populated on Vercel.
- [ ] Sentinel allocator EOA `0x0A7d0343…` holds ≥ 3.5 KITE.
- [ ] Deployer EOA holds ≥ 10 KITE for paymaster sponsorship +
      scenario-mode top-ups.
- [ ] mr.kite still has live `TradeAttested` events queryable on
      Goldsky `helios/v0.9.0` — one verify-trade.js dry run before
      the session passes.
- [ ] Goldsky subgraphs healthy: `helios/v0.9.0`,
      `helios-base/v0.8.0`, `helios-arbitrum/v0.8.0`.
- [ ] Browser tabs pre-arranged in order:
      (1) frontend, (2) Goldsky GraphQL, (3) Kitescan,
      (4) LZScan, (5) terminal.
- [ ] One sloppy dry-run capture (no audio) to expose any
      tab-switching, transition, or scenario-mode timing issues.

---

## Verification

After this script is committed:

1. **Word-rate audit.** Per-beat words ÷ seconds → confirm
   90–155 wpm per beat (the readable-on-video range).
2. **Stopwatch read-through.** Read aloud against a stopwatch, no
   recording. Confirm total ≤ 4:00.
3. **Per-beat surface check.** Open every URL / CLI on the live
   deploy and confirm every on-screen item still exists.
4. **Outside-reader test.** Hand the script to one person and ask:
   "what does Helios do?" Answer within 30s of finishing reading =
   preamble works. If not, rewrite the preamble.

---

## Source material index

For the video editor preparing assets in advance:

| Asset | Source |
|---|---|
| Landing-page LandingStatsBand | live Vercel deploy |
| `/onboard` Passport flow | `frontend/src/components/onboard/OnboardClient.tsx` |
| `/dashboard` activity rail | `frontend/src/components/dashboard/ActivityRail.tsx` (event labels) |
| `/strategies` leaderboard | `frontend/src/app/strategies/page.tsx` |
| `/audit/strategy/[id]` breakdown | `frontend/src/app/audit/strategy/[id]/page.tsx` |
| `/judge` verify-trade block | `frontend/src/app/judge/page.tsx` |
| `verify-trade.js` CLI | `scripts/verify-trade.js` |
| mr.kite vault | `0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a` (Kite) |
| AllocatorVault | `0xf3e4452fe17edbfa6833022b9c186aa14b98955d` (Kite) |
| ReputationAnchor V2-bis | `0x2b6c5f3648Ae2aA27c80CB871590D1Ef1346938D` (Kite) |
| Cross-chain hop txs (fallback) | `0x6ef584a1…`, `0xfee792dc…`, `0xcda2e6bd…` |
| Cross-chain reputation evidence | LZ GUID `0x24fd5344…` (Base → Kite) |
