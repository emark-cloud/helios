# Helios demo runbook — capturing the WS5 video

> **Purpose.** Operational procedure for capturing the pre-recorded
> 4-minute demo described in [`docs/demo-script.md`](./demo-script.md).
> The script is the *what*; this runbook is the *how*.

---

## Equipment

- Screen-recording software with per-window capture (OBS, Loom, or
  built-in macOS Screenshot is fine).
- Microphone — USB condenser preferred; built-in laptop mic is the
  fallback. Record voiceover separately in post unless you've done
  live narration before.
- Browser with a clean profile slot (Brave / Chrome / Firefox — any
  WebAuthn-capable). Passport requires a passkey-capable device.
- Terminal with a large font (≥ 18pt) and a high-contrast theme.
- Two monitors (primary capture + cheat-sheet / chat) ideal but not
  required.

---

## Pre-flight (T-2h)

Run through this list **before** opening the screen recorder. Each
unchecked item is a known failure mode for one of the beats.

### Stack health

- [ ] VPS sentinel image is current `main`. Verify with:
      `ssh -i ~/.ssh/helios_vps helios@38.49.216.27 \
       'docker images helios/sentinel --format "{{.CreatedSince}}"'`
- [ ] All three Goldsky subgraphs return ≥ 1 row each:
      `helios/v0.9.0`, `helios-base/v0.9.0`,
      `helios-arbitrum/v0.9.0`.
- [ ] mr.kite (`0x1717640c…`) has a `TradeAttested` event with a
      timestamp within the last 24 h. Dry-run check:
      `node scripts/verify-trade.js <tx-hash>` → exit 0.
- [ ] Vercel frontend is on latest `main`; `NEXT_PUBLIC_USE_PASSPORT=1`;
      `NEXT_PUBLIC_PARTICLE_*` populated.

### Funding

- [ ] No Sentinel-allocator KITE gate for Beat 2 — cross-chain
      capital is OFF in v1, so the `OFT.send` bridge path (which
      burned ~1 KITE per LZ V2 hop) never runs. Beat 2 is now
      Kite-local allocation only.
- [ ] Deployer EOA holds ≥ 10 KITE for paymaster sponsorship of the
      onboarding userOp + Kite-local `allocateToStrategy` gas +
      scenario-mode top-ups.
- [ ] Fresh demo wallet for Beat 1 has zero balance and zero
      transaction history (Passport flow shows from zero state).

### Browser state

- [ ] Recording browser profile fully reset: clear localStorage,
      sessionStorage, IndexedDB, cookies. **Do not pop incognito** —
      Passport's AA-salt cache behaves differently there.
- [ ] Five tabs pre-arranged, in this order:
      1. Live frontend (landing page)
      2. Goldsky GraphQL playground with the Beat 3 query pre-typed
      3. Kitescan
      4. LZScan (`https://testnet.layerzeroscan.com`)
      5. Local terminal with `node scripts/verify-trade.js` typed
         but **not** executed
- [ ] Browser zoom = 100%; window size 1920 × 1080 minimum.

### Scenario-mode harness (Beat 5 only)

- [ ] Sentinel scenario-mode runner is ready to launch with a price
      trajectory that drops the target vault NAV through the
      drawdown threshold in ≤ 60 s of compressed clock time.
- [ ] The target vault for the scenario take has a current NAV ≥ 2 ×
      drawdown threshold (give the trajectory room to fall).
- [ ] Drawdown threshold is set to a realistic value (15% per
      `Helios.md §14.1`) on the demo wallet's meta-strategy.

### Outside contributors

- [ ] One outside reader confirmed the preamble works (per the
      "Outside-reader test" in `docs/demo-script.md` §Verification).

---

## Capture order

Per `docs/demo-script.md`, take this order — fragile beats first:

1. **Beat 5 — scenario defund.** Largest setup, easiest to break.
2. **Beat 2 — allocation (multi-chain directory, Kite-local
   capital).** Needs a fresh deposit timed against Tier-1 flush
   cadence (~ 5 min). No cross-chain bridge step in v1.
3. **Beat 1 — onboarding.** Fresh browser state, ~ 45 s take.
4. **Beat 3 — verify-trade.js.** Fully deterministic, re-takable.
5. **Beat 4 — cross-chain rep.** Historical evidence, no live action.
6. **Beat 0 + Beat 6 — preamble + close.** Pure screen-cap of the
   landing page + judge page. Last.

Budget ~ 30 min per take including retry cycles + asset capture
(Kitescan screenshots, LZScan trace screenshots). Total recording
session ≈ 3–4 h end to end.

---

## Per-take procedure

For every take:

1. **Stage.** Read the on-screen sequence from `demo-script.md` once
   aloud, then position browser tabs / terminal / Kitescan as that
   beat's section requires.
2. **Arm the recorder.** Capture window scoped to the active
   surface (not the full desktop).
3. **Action.** Execute the on-screen sequence. Speak only if
   recording voiceover live (otherwise the take is silent — narrate
   in post).
4. **Stop & review.** Watch the take back. If any of: tab switch is
   jittery, mouse hovers somewhere distracting, a transaction
   reverts, a 30 s spinner appears — **retake**.
5. **Label & save.** Filename pattern: `beat-N-take-M.mov`. Keep at
   least the last two takes of each beat; trash older ones.
6. **Asset capture.** For each beat, also save:
   - Final Kitescan tx page (full-page screenshot)
   - Goldsky / LZScan view if referenced
   - Terminal output snippet (text, not just screenshot) for the
     verify-trade.js beat

---

## Voiceover

Two options, in order of preference:

**Option A — record voiceover separately.** After all visual takes
are in the can, read the script paragraphs against the visual takes
playing back muted. Adjust on-screen action timing in the editor to
match voiceover pace. Lowest risk, most polish.

**Option B — narrate live during the take.** Doable but every flub
forces a full retake. Only viable if the speaker has already
performed the script aloud against a stopwatch at least 3 times.

In either case, target the per-beat word rates from
`demo-script.md` (90–155 wpm range, beat-specific).

---

## Editing

- Cut on action (tab switch, button click, transaction confirmation
  toast). Avoid mid-pause cuts.
- Title overlays (preamble + closing card): Inter Bold for the body
  text, white on the dashboard's `--ink-deep` background for
  visual continuity.
- Sound: voiceover dialogue ≈ −18 LUFS, no background music
  (mechanism speaks for itself).
- Color: do **not** color-grade the on-screen UI — the design
  tokens are intentional and amber / green / red carry meaning.
- Export: 1080p H.264, target ≤ 50 MB.

---

## Publish

1. Upload final MP4 to a stable URL (YouTube unlisted, Loom, or
   self-host on Vercel).
2. Patch `frontend/src/app/judge/page.tsx` env `DEMO_VIDEO_URL` to
   point at the published video.
3. Update `README.md` line that points at the `/judge` link if the
   URL changes.
4. Commit + push.

---

## Known gotchas

- **Passport AA-salt cache fragility.** The frontend caches the
  Account-Abstraction salt across hot-reloads. A mid-userOp failure
  can leave a corrupt cache that succeeds on retry but lands the
  userOp on a different AA address than expected. Always rotate to
  a fresh browser profile on retry.
- **VPS sentinel in-memory state.** Sentinel does **not** persist
  user state across restarts (no `/srv/helios/data` volume mount).
  If anyone bounces the sentinel container between staging and the
  Beat 2 take, the demo wallet's meta-strategy must be re-POSTed
  via `/tmp/post_meta_strategy.py`.
- **mr.kite quiet period.** If `TradeAttested` cadence pauses (no
  signal from the market), Beat 3 needs a fallback source.
  mom.base and mr.base on Base Sepolia are the next candidates,
  but verify-trade.js needs a Base RPC env override for those.
- **No LZ delivery dependency on Beat 2 (v1).** Cross-chain
  *capital* is OFF, so Beat 2 never waits on a LayerZero hop — the
  `CROSS_CHAIN_ALLOCATION_DEFERRED` event is deterministic and
  instant. LZ executor latency only matters for Beat 4
  (cross-chain reputation), and that beat is captured cold from
  historical on-chain evidence, so no live retake budget needed.
- **Public clone has missing local docs.** `TODO.md` and
  `DESIGN.md` are gitignored. CLAUDE.md still references them. A
  judge cloning the repo cold will see broken links — point them
  at `docs/cold-start.md` instead.
