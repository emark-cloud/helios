# Helios — Pitch deck

> **Format.** 11 slides, 16:9, PowerPoint. Demo-day / mixed audience
> (judges + technical viewers + a stage demo). Product-and-mechanism
> led, honest v1 framing, one forward-looking value slide. No formal
> funding ask.
>
> **Spine.** Problem → the third option → how it works → the
> cryptographic guarantee → portable reputation → the safety
> headline → what's real today → honest cross-chain v1/v2 → where
> value accrues → close. Slide 8 is the live-demo / video slot.
>
> Use alongside `docs/demo-script.md` (the 4-min recorded demo) and
> `docs/demo-runbook.md`. Every on-chain claim here is real and
> independently verifiable — keep it that way; do not round up.

---

## Global design system

Mirror the live product. Everything below maps to
`frontend/src/styles/tokens.css` (single source of truth) and
`DESIGN.md §4 / §13`. Dark-mode only — there is no light variant.

### Palette (exact hex)

| Role | Token | Hex | Use in deck |
|---|---|---|---|
| Page background | `--surface-base` | `#0b1018` | Every slide master. Never pure black. |
| Panel / card | `--surface-panel` | `#131b27` | Content blocks, diagram boxes. |
| Elevated row | `--surface-elev` | `#1a2433` | Highlighted row, callout. |
| Hairline | `--surface-line` | `#1f2a3a` | Dividers, table rules. |
| Primary text | `--fg-primary` | `#e8edf5` | Headlines, numerics. |
| Secondary text | `--fg-secondary` | `#b3becf` | Body. |
| Muted text | `--fg-muted` | `#808dab` | Labels, captions, axis ticks. |
| **Accent — amber** | `--accent-amber` | `#d99a2b` | THE only non-neutral color. ≤ 2–5 % of pixels per slide. Active state, one key word, CTA, verified badge, the user's capital thread. |
| Amber bright | `--accent-amber-bright` | `#f0b248` | Hover / emphasis only. |
| Signal positive | `--signal-positive` | `#6cb486` | Numeric direction ONLY (NAV up, PnL+). Never a button or decoration. |
| Signal negative | `--signal-negative` | `#e87b6e` | Numeric direction / the defund row marker only. |
| Chain — Kite | `--chain-kite` | `#d99a2b` | Kite borrows the amber: Kite is home. |
| Chain — Base | `--chain-base` | `#4d7cd1` | Chain badge only, low saturation. |
| Chain — Arbitrum | `--chain-arbitrum` | `#5396b8` | Chain badge only, low saturation. |

**Discipline (non-negotiable, this is the brand):** amber is scarce
— if a slide looks amber-heavy, it's wrong. Green/red are *data
signal only*; a green checkmark or a red arrow is fine, a green
button is not. Chains are muted, never loud.

### Type

- **Body / headlines:** IBM Plex Sans (400–600).
- **All on-chain data** — addresses, tx hashes, NAV figures, public
  inputs, code: IBM Plex Mono, with tabular figures (`tnum`).
  Treat every hash/number as mono. This is a visual signature.
- **Editorial moments only** (title slide, one pull-quote):
  Instrument Serif *italic*. Use exactly twice in the whole deck.
- Embed fonts in the .pptx (File → Options → Save → *Embed fonts in
  the file*). Fallbacks if the presenter machine lacks them:
  Plex Sans → Inter/Arial, Plex Mono → SF Mono/Consolas,
  Instrument Serif → a transitional serif.

### Motion (if animating builds)

The product's rule: **mechanical, not smooth.** Anything that maps
to a discrete on-chain event uses a hard cut / instant appear — no
fades, no eased motion. Reserve PowerPoint "Fade/Morph" for
narrative transitions between slides; use "Appear" (instant) for any
element representing an event, proof, or tick. Per-digit NAV ticks,
if shown, step at ~30 ms. Honor reduced-motion if presenting to a
recorded format: prefer cuts over animation entirely.

### Layout grid

- 12-col grid, generous page margins (calm at the page level), tight
  spacing *inside* panels (Bloomberg density inside cards — the
  product's signature contrast).
- One idea per slide. Headline ≤ 7 words. ≤ 3 supporting lines.
- Bottom-left: small mono kicker (slide topic). Bottom-right: slide
  number in muted mono. Consistent across all slides.
- Real artifacts (tx hashes, addresses, query output) are the
  visual texture — show actual mono strings, lightly truncated
  (`0x1717640c…`), never lorem-ipsum placeholders.

---

## Slide 1 — Title / hook

**Headline:** Helios

**Sub (Instrument Serif italic, the editorial moment):**
*A programmatic capital market for AI trading agents.*

**One line under it (Plex Sans, fg-secondary):**
Every trade carries a zero-knowledge proof. Reputation is earned,
attested, and portable. The user signs once.

**On slide:** Near-black `#0b1018` field. Wordmark large, centered
slightly high. A single thin amber underline under one word
("proof" or the wordmark) — the *only* amber on the slide. Faint
mono ticker strip along the bottom edge showing a real strategy row
(`mean_reversion_v1 · Kite · rep 0.74`) at ~12 % opacity, like the
live `LandingStatsBand` bleeding through.

**Speaker note (10 s):** "Helios is a market where AI agents compete
for real user capital — and cryptography, not trust, is what keeps
them honest."

---

## Slide 2 — The problem

**Headline:** Two bad options

**Body (two columns, equal weight, panel cards):**
- **Trust the black box.** Hand capital to an opaque AI pool. No
  proof of what it actually did. No recourse when it drifts.
- **Babysit it yourself.** Run the strategy, watch the screen, pull
  the plug manually. Doesn't scale. You sleep; the market doesn't.

**Pull-line under both (fg-muted):** AI agents are managing real
capital *today*. Both options ask the user to either give up control
or give up their life.

**On slide:** Two `#131b27` panels, a thin `#1f2a3a` divider
between. No color — deliberately flat and grey. The greyness is the
point; the next slide is where amber first appears.

**Speaker note:** "This isn't hypothetical — agents trade real money
now. The user's only choices are blind trust or constant vigilance."

---

## Slide 3 — The third option

**Headline:** Helios is a third option

**Body (3 tight lines, each with a mono keyword in amber):**
- Agents **compete** in an open market for delegated capital.
- Every trade is bound to a declared strategy class by a
  **`ZK proof`** — the chain rejects off-class trades.
- A bad strategy is **`permissionless`** to shut down — anyone can,
  no one can suppress it.

**Closing line (Plex Sans, primary):** The user signs one
meta-strategy. The protocol enforces everything else.

**On slide:** Single centered panel. First real amber of the deck —
only on the three mono keywords (`ZK proof`, `permissionless`, and
the verb `compete`). Everything else neutral. This slide is the
hinge: grey problem → enforced solution.

**Speaker note:** "Not trust, not babysitting — enforcement. The
user delegates intent; math and on-chain rules do the rest."

---

## Slide 4 — How it works

**Headline:** One signature, an autonomous market

**Diagram (left→right flow, mono labels, muted connectors):**

```
 User ──signs once──▶ Meta-strategy (Kite Passport passkey, MPC, gas-sponsored)
                           │
                           ▼
                   Allocator Agent  ──ranks & routes──▶  Strategy Agents
                  (Sentinel, reference)                   (compete for capital)
                           │                                     │
                           ▼                                     ▼
                   UserVault / AllocatorVault            StrategyVault + ZK proof per trade
                           │                                     │
                           └──────────── Reputation ◀────────────┘
                                   (realized, attested, on-chain)
```

**Three captions under it (fg-muted, mono):**
- `Sign:` one Passport passkey, one userOp, four atomic on-chain
  calls. No seed phrase, gas sponsored.
- `Route:` allocator ranks strategies by realized performance +
  stake, sizes positions, rebalances.
- `Prove:` every strategy trade emits a Groth16 proof + an event;
  the subgraph indexes it.

**On slide:** Nodes are `#131b27` panels with `#1f2a3a` borders.
The user→meta-strategy edge is the single amber thread (the user's
capital). Everything else neutral grey connectors. Chain badges only
appear on Strategy Agents (Kite amber / Base blue / Arb teal).

**Speaker note:** "Four roles: user, allocator, strategies, vaults.
The user appears once, at the top. After that the protocol runs
itself."

---

## Slide 5 — The cryptographic guarantee

**Headline:** The agent literally cannot lie

**Body (problem→mechanism, one beat each):**
- A momentum agent could *say* it's momentum and quietly run
  something riskier. Disclosure doesn't stop that. **Math does.**
- Every trade ships a **Groth16 zero-knowledge proof** binding it to
  the strategy's declared class. ~8,000 circuit constraints encode
  the class invariants. The on-chain verifier **rejects the
  transaction before it lands** if the trade is off-class.
- Three live circuit classes: `momentum_v1`,
  `mean_reversion_v1`, `yield_rotation_v1`.

**Proof strip (mono, bottom — make it real):**
`verify-trade.js <tx>` → fetch receipt → decode proof → re-run
verifier locally → `PROOF VALID ✓` in ~40 ms. Anyone can run it.

**On slide:** A real `publicInputs` array shown in mono, one field
amber-highlighted (`declared_class = mean_reversion_v1`). A small
amber "verified" tick — the *only* amber. This is the moat slide;
let the mono texture carry it.

**Speaker note:** "This is the core. Not 'trust our model' —
're-run the verifier yourself, the chain already did.' Same verifier
covers our Claude-driven reference strategy: model decides, chain
enforces."

---

## Slide 6 — Reputation that travels

**Headline:** Earned, attested, portable

**Body:**
- Reputation accrues only from **realized, attested** performance —
  not promises, not backtests. Formula is specified
  (`Helios.md §8.2`): performance, stake, age, consistency,
  risk-adjustment.
- It lives canonically on Kite but strategies trade where the venue
  is best — Base for spot, Arbitrum for yield.
- **LayerZero V2 carries reputation across chains.** A Base strategy
  earns its track record on Uniswap; that score lands on Kite as one
  signed message. Trust is portable even in v1.

**Small fact chip (mono, fg-muted):** Cross-chain reputation
propagation is live and effectively free — Base/Arb-Sepolia testnet
ETH, ~`9.9e-5 ETH` per message, no scarce Kite gas.

**On slide:** Three chain badges (Kite amber / Base `#4d7cd1` / Arb
`#5396b8`) with thin connectors converging on a single Kite node.
Connectors muted; the convergence point gets a faint amber ring.

**Speaker note:** "Identity and reputation are already
multi-chain. A strategy's reputation follows it, signed, wherever
it trades."

---

## Slide 7 — The safety headline: permissionless auto-defund

**Headline:** No one can trap the user's capital

**Body:**
- The user sets a drawdown threshold once. If a strategy breaches
  it, the defund is **permissionless** — *anyone* can fire it.
- Sentinel does, in normal operation. If Sentinel is offline, the
  user can. If the user is asleep, anyone else can — there's a bond
  + reward making it economically rational to.
- The mechanism is on-chain. The proof is in the receipt. Capital
  reroutes automatically. **No party can suppress it.**

**Event sequence (mono, stepped — use instant "Appear", not fade):**
`DEFUND_ARMED` → `DEFUND_TRIGGERED` → `STRATEGY_DEACTIVATED` →
`Allocation` (capital rerouted, chain-local)

**On slide:** The defund row uses the product's literal marker — a
3 px `#e87b6e` left border (`--border-defund`). That red is the only
non-neutral here and it's *data signal*, exactly as the product
uses it. Steps reveal as hard cuts, never eased.

**Speaker note (the headline beat):** "This is the part that
matters. Safety isn't a promise from us — it's a permissionless
function anyone can call. The protocol acts even if we don't."

---

## Slide 8 — Live demo / proof it's real

**Headline:** This is live. Verify it yourself.

**This is the demo slot.** Either: (a) cut to the 4-min recorded
demo (`docs/demo-script.md`), or (b) screen-share the live deploy.
The slide is the backboard while the demo runs / a static fallback.

**Static fallback content (real artifacts, all mono):**
- Kite testnet (chain `2368`) — 6 canonical strategies live across
  3 chains: 3 Kite, 2 Base, 1 Arbitrum.
- First autonomous on-chain `TradeAttested`: `2026-05-12`,
  `mean_reversion_v1` (`0x1717640c…`).
- Real Kite Passport onboarding: passkey, MPC wallet, sponsored gas.
- Public SDKs on PyPI: `helios-strategy-sdk`,
  `helios-allocator-sdk` — anyone can ship a competing agent.
- Subgraph `helios/v0.9.0` on Goldsky · `/judge` page ships the
  one-command trade verifier.

**On slide:** A grid of small mono "evidence chips," each a real
value. One amber chip: "Run `verify-trade.js` yourself." No prose —
this slide is texture and credibility.

**Speaker note:** "Everything you just saw is on a public testnet
with a public verifier. Don't take our word — there's a CLI."

---

## Slide 9 — Cross-chain: honest v1, deliberate v2

**Headline:** Multi-chain by identity, chain-local by capital — for now

**Two-column, explicitly honest:**

| Live in v1 | Deliberate v2 |
|---|---|
| Strategies span Kite + Base + Arbitrum | Cross-chain *capital* allocation |
| Reputation propagates cross-chain (LZ V2) | Kite as a read-only accounting roll-up |
| Identity is unified on Kite | Users deposit directly on their chosen chain |
| Capital is **chain-local** (no bridge) | Principal & fees never cross a chain |

**The honest line (fg-secondary, do not soften):** We turned
per-rebalance cross-chain *capital* bridging **off** in v1 — the
fixed LayerZero fee made it impractical on testnet, and we'd rather
ship a real boundary than a leaky one. Identity and reputation are
already cross-chain; cross-chain capital is a *documented, designed*
v2 — not a TODO. Spec: `Helios.md §12`,
`docs/cross-chain-cost-roadmap.md`.

**On slide:** Two panels, "Live" panel slightly elevated
(`#1a2433`) and bordered, "v2" panel flat. A single amber arrow from
v1→v2 labeled "designed, not deferred." Credibility comes from
*saying the boundary out loud*.

**Speaker note:** "We'd rather show you a sharp edge than pretend it
isn't there. Cross-chain capital is engineered for v2 with the
economics worked out — it's in the spec, not a wishlist."

---

## Slide 10 — Where value accrues

**Headline:** A market with natural toll booths

> Forward-looking, not a raise. Framed as "where value *can*
> accrue," grounded in mechanisms that already exist on-chain.

**Three value surfaces (each tied to a real mechanism):**
- **Performance-fee split.** The protocol already settles realized
  performance fees on-chain (`FEE_SETTLED`). A protocol cut on
  realized — not paper — PnL is the natural, aligned toll: Helios
  earns only when the user does.
- **Allocator marketplace.** Allocators compete via the public
  `allocator-sdk`. Listing / routing / premium-tier economics for
  third-party allocators is a marketplace, not a single product.
- **Reputation as infrastructure.** An attested, cross-chain
  performance ledger for AI agents is reusable beyond Helios —
  other protocols could consume it.

**One line (fg-muted):** Every surface is incentive-aligned:
Helios captures value only on *realized, attested* outcomes — the
same thing the user is paying for.

**On slide:** Three minimal columns, mono labels for the on-chain
hook (`FEE_SETTLED`, `allocator-sdk`, `ReputationAnchor`). At most
one amber accent (the word "aligned"). Restrained — this is a
direction, not a model with fake numbers.

**Speaker note:** "We're not pitching a token slide. The point is
the value capture is structurally aligned — fees only on realized
performance, and there are several real toll booths in an open
market."

---

## Slide 11 — Close

**Headline:** Programmable capital, cryptographically enforced.

**Sub (Instrument Serif italic — the second and final editorial
moment):** *Live on Kite. Verify everything yourself.*

**Three mono links, fg-secondary:**
- Live deploy: `<vercel-url>`
- Code: `github.com/emark-cloud/helios`
- Verify a trade: `node scripts/verify-trade.js <tx>`

**On slide:** Mirror of the title slide — same composition, same
single amber underline, the faint live ticker bleeding through the
bottom. Bookends the deck. The repeated motif signals "the thing you
saw at the start is real and running now."

**Speaker note (12 s):** "Helios. The user signs once; the protocol
proves the rest. It's live on Kite testnet — and every claim in this
deck has a transaction behind it."

---

## Optional appendix slides (have ready, don't present unless asked)

Demo-day Q&A tends to probe these. Build them; keep them after
slide 11; pull them up only on the question.

- **A1 — ZK circuit detail.** Constraint counts, PTAU headroom,
  16 public inputs, the cross-decimal slippage constraint. For the
  technical judge who asks "what's actually in the circuit."
- **A2 — Reputation math.** The `§8.2` weighted formula expanded,
  componentsHash, anti-gaming. For "how do you stop reputation
  farming."
- **A3 — Threat model.** Permissionless-defund griefing + bond
  economics, oracle trust, allocator misbehavior bounds. For "what
  breaks this."
- **A4 — Kite-native.** Why this is built for Kite specifically:
  Passport passkey/MPC/x402, sponsored gas, the agent-economy
  thesis. For "why Kite."
- **A5 — Architecture / repo map.** Contracts, circuits, SDKs,
  services, subgraph, frontend — the full surface, for "show me the
  system."

---

## Build & export checklist

- [ ] 16:9 (13.333 in × 7.5 in). Dark master slide, bg `#0b1018`.
- [ ] Fonts embedded (Plex Sans, Plex Mono, Instrument Serif) — or
      substituted per the fallback list. Verify on the presenter
      machine before the room.
- [ ] Amber audited per slide: ≤ 2–5 % of pixels. If a slide feels
      amber-heavy, cut it back. Slides 2 and 9-left should be near
      colorless on purpose.
- [ ] Green/red appear ONLY as data signal (slide 7 defund marker,
      any NAV figure). Never on a shape or button.
- [ ] Every hash / address / number is mono with tabular figures
      and is a *real* value, lightly truncated — no placeholders.
- [ ] Event-mapped elements use instant "Appear," not fade/morph.
- [ ] Slide 8 demo path tested end to end (recorded fallback AND
      live) per `docs/demo-runbook.md`.
- [ ] Every on-chain claim re-verified against the live deploy the
      day of — addresses and counts drift; this doc's numbers are
      current as of the cross-chain-capital-off cutover (2026-05-17)
      and the 6-canonical-strategy directory.
- [ ] Read-through against a stopwatch: ~10–12 min for 11 slides
      leaves room for the demo + Q&A in a typical demo-day slot.
