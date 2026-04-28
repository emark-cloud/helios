# Helios — Design Brief

**A design brief for the Helios v1 interface. Written for the designer, not the implementer.**

> Companion to `SPEC.md` (which defines the product). This document defines what Helios should *feel like*, what problems the design must solve, and where the non-negotiables are. Craft decisions — type pairings, exact color values, component edge treatments, layout rhythm — belong to you. The problems, the constraints, and the voice are defined below.

---

## Table of contents

1. [The product, in one paragraph](#1-the-product-in-one-paragraph)
2. [Who this is for](#2-who-this-is-for)
3. [The one unforgettable thing](#3-the-one-unforgettable-thing)
4. [Aesthetic direction](#4-aesthetic-direction)
5. [Design principles](#5-design-principles)
6. [Voice and tone](#6-voice-and-tone)
7. [What to avoid](#7-what-to-avoid)
8. [The design problems](#8-the-design-problems)
9. [Key surfaces](#9-key-surfaces)
10. [Signature interactions](#10-signature-interactions)
11. [The sunburst — our one piece of bespoke visualization](#11-the-sunburst--our-one-piece-of-bespoke-visualization)
12. [ZK verification — how visible](#12-zk-verification--how-visible)
13. [Motion philosophy](#13-motion-philosophy)
14. [Constraints and non-negotiables](#14-constraints-and-non-negotiables)
15. [Telegram bot](#15-telegram-bot)
16. [What I need back from you](#16-what-i-need-back-from-you)

---

## 1. The product, in one paragraph

Helios is a programmatic capital market for AI trading agents. A user signs one meta-strategy, and an allocator agent autonomously routes their capital across competing trading strategies — rewarding the best performers, firing the worst. Every trade carries a cryptographic proof that it matches the strategy's declared class. It's a trader's instrument, not a consumer product. Users come with serious money and serious questions: *Where is my capital right now? What's it doing? Who's managing it? What rules are they operating under? Can I trust what I'm seeing?* Every page answers these.

Read `SPEC.md` for the technical depth. For design purposes, what matters is: this is infrastructure for people who already know what a Sharpe ratio is, and who have been burned before by opaque "AI-managed" products.

---

## 2. Who this is for

Three audiences, roughly ordered by priority during the hackathon:

**Hackathon judges** — technical, skeptical, 5-minute attention budget per submission. They need to understand what Helios does and why it's credible within minutes. First impressions count doubly.

**Capital owners** — crypto-native individuals with $5k-$100k to deploy, who've already tried managing DeFi positions and want the hands-off version but without custody loss. They read Sharpe ratios and drawdown charts naturally. They don't need hand-holding, but they do need to trust what they see.

**Strategy and allocator operators** — quant developers and portfolio managers who deploy strategies and allocators to the marketplace. They're the power users. Interface density serves them.

We design *to* capital owners and operators. Judges come along for the ride because good design for professionals also reads as serious design to judges.

**Who this is NOT for:**
- Retail users looking for a yield app (the mental model is wrong)
- First-time DeFi users (this is not an onboarding product)
- Mobile-first users (see §14)

---

## 3. The one unforgettable thing

Helios has one signature moment the whole design is organized around: **the auto-defund**.

When a strategy breaches its drawdown threshold, the system fires it autonomously. Capital migrates to a replacement strategy in seconds. No human presses a button.

Design this moment until it feels inevitable. It should land with the quiet satisfaction of watching a well-engineered system do exactly what it said it would do — not with drama, not with alarms. A red edge lighting up. A number stepping down. Capital visibly relocating. A telegram ping. The user's portfolio shape changes, and the system returns to calm.

If a judge leaves having remembered one thing, it should be this moment. Every other design decision either supports it or gets out of its way.

---

## 4. Aesthetic direction

### 4.1 The one-line signature

**A professional trader's instrument that respects your eyes.** Bloomberg's information density, Vercel v0's breathing room, charcoal and deep navy with a single amber accent.

### 4.2 Reference products

In order of relevance. Not instructions to copy — these are the aesthetic coordinates you're navigating around.

**Primary anchors:**

- **Bloomberg Terminal** — for tabular data discipline, monospace numerics, color-as-signal, keyboard-first navigation, chronological event logs treated as first-class content
- **Vercel v0 / Vercel Dashboard** — for component edge treatment, restraint, generous spacing between dense elements, modern sans-serif voice, the "expensive but not showy" feel

**Secondary anchors:**

- **Linear** — for the overall calm, the refusal to decorate, the keyboard ethos
- **Drift Protocol** — for adapting trader-tool density to a modern web stack without looking like a 1990s terminal
- **Hyperliquid** — for the darkness, though Helios should feel warmer and more considered

**Explicit non-references:**

- Uniswap, PancakeSwap, and most retail DeFi apps (wrong audience, wrong tone — too playful, too colorful)
- Robinhood, eToro (wrong audience — retail)
- Most "Web3 startup" landing pages (gradients, glass, neon)

### 4.3 The color direction

**Charcoal and deep navy** base — not pure black. A near-black that has faint blue undertones, so it reads as "night panel" rather than "void." Panels sit one step up from the base. Elevation is achieved through subtle value shifts, never shadows with color, never glow.

**One amber accent.** Helios is named for the sun; amber is the only non-neutral color in the system. It's used for active states, selected rows, primary CTAs, focus rings, verified-proof badges, and the "user's capital" threads in the sunburst viz. Nothing else. Amber in roughly 2–5% of visible pixels. If you find yourself wanting more amber, treat it as a signal that hierarchy is failing elsewhere.

**Green and red for data signal only.** Positive numbers, negative numbers, drawdown zones, verification pass/fail. These colors carry meaning; they never appear on buttons, generic status dots, or decorative elements. A calm green (not neon), a warm red (not alarming).

**Chain indicators.** Kite, Base, and Arbitrum each have a muted chain-color used only in chain badges. Kite borrows the amber intentionally — Kite is home.

### 4.4 Typography direction

The type system should do three things:

1. **Establish a distinctive voice** — not Inter, not Roboto, not SF Pro. These are the generic defaults designers reach for and they make Helios look like every other SaaS product. Choose fonts with real character. Variable fonts preferred.

2. **Treat numerics as first-class.** Every balance, P&L, NAV, fee, percentage, timestamp renders in a monospace face with tabular figures. When a user scans a column of 47 strategy NAVs, the decimal column must align perfectly. This single decision differentiates Helios from most DeFi UIs visually.

3. **Optionally introduce a third voice for editorial moments.** The landing hero and the audit page could use a distinct serif or display face for one-off high-impact text — treated as a signal of gravitas. Use sparingly or not at all.

Pair the body/display sans with its sibling monospace where possible (e.g., JetBrains Sans + JetBrains Mono, or Söhne + Söhne Mono) to avoid mismatched proportions between prose and numerics.

### 4.5 Density on the "density vs. calm" axis

**Halfway, with a deliberate split.**

- **Landing, onboarding, meta-strategy builder, allocator picker:** calm. Generous spacing, confident headlines, one thing at a time. Vercel-side of the aesthetic.
- **Dashboard, strategies directory, strategy detail, audit page:** dense. Tables as primary surface, tight row heights, multiple data points per card, chronological event streams. Bloomberg-side of the aesthetic.

The density lives *at the component level* (tight tables, compact stat cards). Page grids stay breathable — generous margins between components, clear sectioning. The net effect: you can see a lot of information without feeling assaulted.

---

## 5. Design principles

Eight principles. Every design decision should trace to at least one.

### 5.1 Data before decoration

If a pixel isn't carrying meaning, it shouldn't be there. No illustrative imagery. No stock icons filling space. No background textures for depth. The visual richness of Helios comes from well-presented data — aligned numerics, disciplined typography, meaningful color. Professional restraint reads as credibility; decoration reads as compensation.

### 5.2 Color as signal, not decoration

Amber = active/selected/verified. Green = positive value. Red = negative value or breach. Nothing gets colored "because it looks nice." If you add color somewhere, be able to state what information it's carrying.

### 5.3 Monospace where numbers align

Not stylistic — functional. Users scan columns of numbers constantly. Proportional numerics force re-reading every row. Tabular mono lets the eye trace a single column in one fixation.

### 5.4 Density at the component level, calm at the page level

Tight rows, generous margins between containers. You can violate this deliberately for specific pages (landing is all calm; audit page might be all density). But the default is the mix.

### 5.5 Keyboard first

Every common action has a hotkey. Lists navigate with `J/K`. `/` focuses search. `Esc` closes. `G D` jumps to dashboard, `G S` to strategies, `G A` to allocators. Hotkeys are discoverable via `?`. Codifying "professional tool" into the interaction model.

### 5.6 Motion is mechanical

When Helios animates, it's because the system *did* something. Capital cascades → staggered appearance (because capital cascades in staggered transactions). NAV updates → digit-stepping (because prices update in ticks). Nothing eases smoothly when the underlying behavior is discrete. No hover-state easings over 150ms. Animation budget spends on three moments (cascade, defund, reputation) and essentially nowhere else.

### 5.7 Four questions in the top-left of every page

What am I looking at? What's the current state? What's changed recently? What can I do? Structural consistency is what makes a power-user tool feel learnable after twenty minutes.

### 5.8 Bloomberg density ≠ Bloomberg ugliness

Bloomberg earned its density through decades of necessity. Helios earns its density through typographic discipline, color restraint, and hierarchy. If a screen starts feeling cluttered, the failure is in hierarchy — not in information volume. Sharpen type scale and color discipline, don't remove data.

---

## 6. Voice and tone

Helios speaks with **quiet authority**. Every piece of UI copy should read like it was written by someone who knows what they're doing and doesn't feel the need to prove it.

**Do:**
- "Allocation complete. $1,000 deployed across 4 strategies."
- "MomentumKite-A defunded. Drawdown threshold breached."
- "Review your meta-strategy below. Sign once."
- "Strategy MomentumKite-A — Momentum v1, Kite, $127k managed"

**Don't:**
- "🎉 You allocated successfully!"
- "Oops! Looks like something went wrong."
- "Your AI is working hard for you!"
- "Get started earning passive income now"

**Error messages are direct.** "Stake below minimum. Top up 0.5 KITE to proceed." — not "Uh oh! We couldn't complete that action."

**Numeric context is provided, not hidden.** Dashboard says "Net P&L: +$127.40 (+1.27%) since first allocation." Not just "+$127.40" and definitely not "Doing great! 🚀"

**Professional does not mean cold.** "Welcome back, Maya" is fine. "Hey Maya! 👋 Good to see you!" is not.

No emoji in the product UI. (Telegram bot is a separate question — see §15.)

---

## 7. What to avoid

Concrete list of failure modes to steer around:

**Visual:**
- ✗ Purple gradients of any kind. The lazy crypto default. We are not that.
- ✗ Glassmorphism, frosted surfaces, backdrop-blur effects
- ✗ Neon glows, colored drop shadows, aura effects
- ✗ Gradient text, rainbow accents, "Web3 style"
- ✗ Inter, Roboto, SF Pro, Arial as primary type
- ✗ Stock iconography (Heroicons, Feather, etc. as-is — if using icon libraries, restyle them to match the system)
- ✗ Animated hero backgrounds (shader loops, particle systems, rotating 3D shapes)
- ✗ Full-page loading spinners; use skeleton states
- ✗ Pill-shaped gradient-filled buttons
- ✗ Cutesy mascots, 3D renders, robot avatars, "AI-feeling" imagery

**Tonal:**
- ✗ Emoji in product UI
- ✗ Exclamation marks in system messages
- ✗ "Oops" or "uh oh" language
- ✗ "Passive income", "earn while you sleep", retail-yield framing
- ✗ Friendly mascot-style voice

**Structural:**
- ✗ Tabs when a sidebar would work (tabs hide information)
- ✗ Accordion menus on desktop for primary navigation
- ✗ Modal dialogs for anything beyond destructive confirmations
- ✗ Hamburger menus on desktop
- ✗ Auto-rotating carousels
- ✗ Carousels generally

If you disagree with any of these and have a reason, flag it in review rather than just violating silently. Some are absolute (no purple gradients), others are defaults that could theoretically be overridden (emoji in one specific place for one specific reason).

---

## 8. The design problems

These are the real problems the design has to solve. The good design is the one that solves these; the pretty design that doesn't isn't.

### 8.1 Make it obvious, within 10 seconds, that this is different from "another AI trading bot"

The hackathon judges and serious users will have seen dozens of AI trading products. What distinguishes Helios is (a) the marketplace structure — many strategies competing, capital flowing to winners — and (b) the cryptographic proof that strategies behave as declared. The landing and the dashboard must communicate this without requiring anyone to read text carefully.

Possible directions (not prescriptions): a landing that leads with a live stats band showing current managed capital, active strategies, attested trades; a dashboard that foregrounds the marketplace shape (multiple strategies ranked, reputation scores, live activity); the sunburst viz giving an immediate mental model of capital-flowing-to-performers.

### 8.2 Give users confidence their capital isn't lost in a black box

AI-managed capital products lose trust when users can't see what's happening. Helios has radical transparency baked in — every trade is attested, every rule is enforced on-chain, every strategy's P&L is public. The design must surface this.

Possible directions: a "portfolio breathing" treatment where live activity is visible at a glance on the dashboard; a strategy detail page that shows the current position, recent trades, and most-recent proof verification inline; a persistent audit link from any strategy to its full trade history.

### 8.3 Make the auto-defund moment land

This is the signature moment (§3). It needs to happen in a way that:
- Is visible from the main dashboard (no hunting)
- Makes clear what just happened and why
- Shows the replacement allocation happening
- Doesn't feel alarming (this is the system working correctly, not an emergency)

Possible directions: a persistent "recent activity" rail on the dashboard that pulses when an event happens; the strategy row itself transforming (color shift, capital visibly draining); the sunburst viz re-balancing in view.

### 8.4 Communicate the two-sided market

Helios has two markets happening simultaneously: strategies competing for allocator capital, and allocators competing for user delegations. Users will see both. The design must make the two-level structure legible — otherwise users will think it's just "a list of strategies" and miss the allocator layer.

Possible directions: a navigation that names both "Strategies" and "Allocators" as peer concepts; an onboarding flow that shows the user their "allocator → strategies" tree when they sign; the dashboard explicitly showing "Allocator: Helios Sentinel" as a piece of UI that's tappable to learn more.

### 8.5 Make the 5-minute judge evaluation trivial

Judges have `/judge` as their entry point. That page has to: give them a video link, a live app link, contract addresses with links, a 5-step evaluation checklist, and a few "proof of real work" signals (transaction count, strategies deployed, cross-chain messages sent). The challenge: making this page feel like a serious document, not a marketing one-pager.

Possible directions: treat it as a press kit. Stark, typographic, link-heavy. No marketing copy. A table of "here's the evidence, go look."

### 8.6 Work on a projector for the demo

The live demo will be projected or shared via video. Small type, low-contrast pairings, and thin strokes disappear. All critical-path surfaces (dashboard, strategy detail, the `/judge` page) must remain legible at lower resolution with some contrast crushing. This is a real constraint — don't let the design pass review at 4K only.

---

## 9. Key surfaces

Every surface below needs a design pass. Not necessarily with equal effort — priority is flagged.

### 9.1 Landing page `/` — priority HIGH

First impression. One screen (desktop) or one tall scroll (mobile). Needs:
- A confident headline that states the thesis
- A live stats band — total capital managed, strategies active, attested trades, active allocators — these are real numbers pulled from the subgraph, not placeholders
- Two primary CTAs: "Enter app" (for users) and "Read the spec" (for judges and operators)
- Secondary links: GitHub, docs, demo video, judge evaluation
- No feature sections, no testimonials, no FAQ

Feel: the landing for an institutional-grade tool. Think Anthropic's homepage more than a typical DeFi landing.

### 9.2 `/onboard` — priority HIGH

The meta-strategy builder. Where a user turns $1,000 and some preferences into a signed commitment. This is the most consequential UX in the product.

Needs:
- Template picker — Conservative / Balanced / Aggressive — each showing the implied constraints as a summary card before selection
- Customization panel — asset universe, max per-strategy, drawdown threshold, max fee rate, rebalance cadence — all editable
- Live preview of what this meta-strategy will do ("this configuration will allocate across roughly 3-5 strategies, with average fee 18%, drawdown circuit at 15%")
- Allocator picker — Sentinel (default) or Helix (alternative), each with a card showing fee, ranking approach, reputation, current users, stake
- A plainspoken summary of the signed commitment, just before the sign button
- The sign button itself — one click, Kite Passport modal, then the cascade begins

Feel: calm, deliberate. The user is about to sign a commitment. No rush. No marketing copy.

### 9.3 `/dashboard` — priority HIGHEST

The user's home. Where the auto-defund moment happens. Where 80% of usage lives.

Needs:
- Top strip: total NAV, today's P&L (%, absolute), all-time P&L, fees-to-date
- Current allocator: who's managing this capital, their fee, their current users, link to their profile
- Active allocations table: each row = one strategy, showing name, chain badge, allocated capital, current NAV, P&L %, drawdown (bar or number), reputation, last activity timestamp
- Live activity rail: chronological event log — allocations, trades, defunds, fee crystallizations, rebalances — with timestamps
- The sunburst viz (see §11) — showing current capital distribution across strategies
- Withdrawal control — always visible, never hidden behind menus

Feel: Bloomberg. Dense, aligned numerics, tabular layout, no wasted pixels inside components, breathing room between them.

### 9.4 `/strategies` — priority HIGH

Public strategies directory. Anyone can browse it without signing in.

Needs:
- Table of all active strategies, filterable by class (momentum / mean-reversion / yield rotation), by chain, by reputation range, by fee rate
- Each row shows: name, class, chain, reputation score (with rank), stake at risk, capacity used, fee rate, 30-day P&L, 30-day Sharpe, 30-day max drawdown, attested trades count, last trade timestamp
- Sorting on every column
- Row click opens strategy detail
- Search by name or operator address

Feel: serious leaderboard. Think PGA tour rankings page, not a marketing "top picks" list.

### 9.5 `/strategies/[id]` — priority HIGH

Individual strategy detail. For operators inspecting competitors and users inspecting holdings.

Needs:
- Manifest header: name, class, operator, chain, registered date, stake, fee rate, capacity, asset universe (as chips)
- Reputation breakdown: the component scores that make up the current reputation (from §8 of the spec) — perf, risk, proof, stake, age — as a small panel
- P&L curve: the one chart that matters — cumulative P&L over time, with drawdown envelope shaded below
- Recent trades table: timestamp, direction, asset in, asset out, size, slippage, proof status (shield icon, clickable to audit), tx hash link
- Current allocators: who's allocated to this strategy and how much
- NAV timeline: secondary chart, shows NAV movements at 1-minute resolution for operators who want to inspect behavior

Feel: a technical product data sheet. Serious. Self-contained.

### 9.6 `/allocators` — priority MEDIUM

Allocator directory. The v1 has Sentinel and Helix; third parties arrive post-hackathon.

Needs:
- List view of all allocators — Sentinel first (with "Official Reference" badge), Helix second (also "Official Reference"), then others
- Each card: name, fee rate, supported strategy classes, ranking function (one-sentence description + "view code" link), current users, total capital managed, reputation score, stake
- The "Official Reference" badge treatment — the one meaningful non-data use of amber
- Side-by-side comparison mode — select 2+ allocators, see their differences in a dense comparison table

Feel: product directory meets leaderboard. Each card reads as a listing for something serious, not a marketplace item.

### 9.7 `/audit/[strategy]` — priority MEDIUM

The auditor view. For judges, serious users, and prospective regulators.

Needs:
- Every trade ever executed by this strategy, paginated — timestamp, tx hash, proof hash, verification result, trade details
- A "verify this proof yourself" CTA — opens a modal explaining the verification command and linking to a standalone verification page
- The reputation calculation exposed: show the inputs (realized P&L, drawdown events, proof validity rate) that produced the current reputation score
- A "download all data" link — JSON dump of every event, for skeptical auditors

Feel: forensic. Document-like. This is where the ZK story gets celebrated (see §12).

### 9.8 `/judge` — priority HIGH (because of hackathon)

The judge evaluation page. 5-minute checklist, everything they need.

Needs:
- Video link at top (3-minute demo, 90-second backup)
- "Try the demo scenario" button — single click, launches the scripted auto-defund scene
- Contract addresses (Kite, Base, Arbitrum) with explorer links (Kitescan / BaseScan / Arbiscan)
- GitHub links (code, SDK, circuits, subgraph)
- A "verify a ZK proof yourself" command block with syntax highlighting
- The 5-step eval checklist from the spec, each with direct links
- Transaction count (live from subgraph): strategies deployed, attested trades, defund events, cross-chain messages, total capital cycled

Feel: a press kit for a technical product. No marketing. Links and facts.

---

## 10. Signature interactions

These three interactions are where design effort concentrates.

### 10.1 The cascade

User signs the meta-strategy. In the next ~15 seconds, capital flows from their wallet into the allocator vault, then into individual strategy vaults, then strategies start executing their first trades.

The interaction should make the hierarchy visible: user → allocator → N strategies. Not as an illustration but as the actual dashboard layout revealing itself. Each stage completes and the next begins — the sunburst grows from the center outward, the strategies table populates row by row, the activity rail prints events as they happen on-chain.

Staggered timing: each strategy allocation appears 80-120ms after the previous. Not because we're adding artificial delay — because the transactions literally confirm in sequence and the UI reflects that.

### 10.2 The auto-defund

The signature moment. A strategy's drawdown breaches threshold. The sequence:

1. The strategy row's drawdown indicator moves through amber into red (not a smooth ease; a discrete tick)
2. The row gets a red left-border — the same edge treatment used for "attention required" but used here for "system acting on its own"
3. Activity rail prints: "MomentumKite-A defunded. Drawdown threshold breached at -15.2%"
4. The allocated capital in that row ticks down to zero over ~2 seconds
5. The sunburst viz re-draws, with the affected segment shrinking and a new one growing elsewhere
6. A new row appears in the allocations table: the replacement strategy with its initial allocation
7. Activity rail prints: "Capital reallocated to MeanRevArb-E ($300)"

The whole sequence is ~5-6 seconds. It should feel like watching a thermostat kick on. No alarms, no flashes, no shake effects. A system behaving correctly.

### 10.3 The cross-chain reputation update

A strategy on Arbitrum lands a profitable trade. Its reputation on Kite needs to update. This involves a LayerZero message, which takes real time (often 30-60s on testnet).

The interaction treats this latency as information rather than hiding it. When the trade lands, the strategy's chain badge briefly pulses once. A small "reputation update in flight" indicator appears on the strategy's row. When the LayerZero message lands on Kite, the reputation score ticks to its new value and the indicator resolves. No deception about the latency, no fake instant update.

---

## 11. The sunburst — our one piece of bespoke visualization

Helios ships one custom visualization: the **sunburst capital-flow diagram**. It appears on the dashboard as the primary portfolio viz, and on allocator detail pages showing the allocator's aggregate capital distribution.

**What it shows:**

Concentric rings. The center is the user (or the allocator, in aggregate view). The first ring is the allocator. The second ring is the strategies, sized by capital allocated. A third ring, optional, shows each strategy's current positions (asset exposure).

**Why sunburst and not a treemap or pie:**

Two reasons. First, it preserves the hierarchical structure visually — user → allocator → strategies → positions — which matches the product's actual architecture. Second, the circular form has thematic resonance with the Helios name without being heavy-handed about it. A sunburst literally is what "Helios" evokes.

**Behavioral requirements:**

- Segments are sized by capital weight
- Segments use the chain-indicator color for chain identification
- The currently-selected segment gets the amber accent treatment
- Hovering a segment reveals strategy name, allocated amount, current NAV, P&L
- Clicking a segment navigates to that strategy's detail page
- When capital flows change (cascade, defund, rebalance), segments animate in size — they don't pop instantly, but they don't ease smoothly either; they step in roughly 300ms of ticked motion
- The viz updates in real-time from the same data source as the allocations table

**What not to do:**

This is not a chart library default. It should look like it was drawn specifically for Helios. The segment edges, the typography of the labels, the hover behavior, the motion on update — all custom. Recharts and Nivo both have sunburst primitives; use them as a starting point but the surface treatment is bespoke.

The viz should also work in a smaller "mini-sunburst" form for card-sized contexts (the allocator card on the allocators page shows each allocator's distribution-at-a-glance as a mini-sunburst).

---

## 12. ZK verification — how visible

Three levels of visibility. The design applies different levels to different surfaces.

**Hidden** — the proofs are plumbing, UI doesn't mention them. Used on: nothing. Every surface at least acknowledges proof status.

**Acknowledged** — a small visual token indicates proof validity. Used on: most product surfaces (dashboard activity rail, strategies table, strategy detail trade log). The treatment is a small shield or similar mark next to each trade. Green shield = valid proof, outline shield = pending, red shield = failed (rare). Click to open a modal with proof details.

**Celebrated** — the ZK story gets full design treatment. Used on: the `/audit/[strategy]` page and the `/judge` page. Here, proof verification gets dedicated visual language — larger shield treatment, visible proof hash, explicit "verified by Groth16" labeling, a "verify this yourself" interaction that launches a modal with a copyable command. The audit page should read as a document about the ZK system, not just as "trade history with shields."

**Tone on the ZK language:**

"ZK-attested" is the primary phrase. "Groth16" is used when technical precision matters (audit page, judge page) but not as the primary consumer-facing term. Avoid both "zero-knowledge proofs" (too academic) and "cryptographically verified" (too vague) as primary labels in the UI.

---

## 13. Motion philosophy

Animation is a budget. Most of it spends on three moments:

1. **The cascade** (§10.1)
2. **The auto-defund** (§10.2)
3. **Cross-chain reputation arrival** (§10.3)

Everything else is either instant (hover states, button presses, menu opens) or static. No 300ms ease-in-out on menu transitions. No scroll-triggered reveals on the landing. No auto-rotating anything.

**Why mechanical over smooth:**

The underlying system is discrete. Trades happen in blocks. NAVs update when events fire. Reputation recomputes on cadence. Smooth easing misrepresents a discrete system as a continuous one. Discrete motion is honest motion.

**What "mechanical" means concretely:**

- NAV digits tick: 30ms per digit step, not a smooth count-up
- Segment resizes step in roughly 4-6 discrete frames over 300ms
- Progress bars fill in 2-3 steps, not a continuous sweep
- Amber-border appearance is instant (no fade-in)
- Activity rail entries appear top-down with 80ms stagger, but each entry itself appears instantly

**The exceptions — where smooth motion is allowed:**

- Sunburst segment rotation to accommodate a new segment (because the geometry requires it)
- Modal overlay fade-in (200ms, standard UI affordance)
- Toast dismissal fade-out (200ms)

That's the entire smooth-motion list. Everything else steps.

---

## 14. Constraints and non-negotiables

### 14.1 Technical constraints

- **Framework:** Next.js 14 (App Router), React 18, TypeScript
- **Styling:** Tailwind CSS. Design tokens exposed as CSS variables; Tailwind config mirrors them.
- **Chart library:** Recharts as base, with custom component wrappers (axes, tooltips, legends styled to match). The sunburst uses Nivo or d3 directly.
- **Icon library:** Lucide, restyled — strokes and weights normalized to the system. Don't ship default Lucide.
- **Wallet:** wagmi v2 + viem. MetaMask, Coinbase Wallet, Rabby support required.
- **Real-time:** WebSocket connection for live events (activity rail, NAV updates, reputation updates). Fallback to polling on disconnect.

### 14.2 Responsive behavior

- **Desktop-first design.** The primary target is 1440px wide.
- **Tablet (768-1024px):** core views (landing, dashboard, strategies, judge) must work. Complex views (audit, allocator comparison) can gracefully degrade.
- **Mobile (<768px):** landing and judge must work. Dashboard and strategies should render readably but density relaxes. Deep tools (audit, meta-strategy builder) can show "desktop recommended" message.

Don't over-invest in mobile polish. The audience is on laptops during serious use.

### 14.3 Accessibility

- WCAG AA contrast minimum on all foreground/background pairs
- Every interactive element reachable via keyboard
- Focus rings visible and amber-toned (not browser default)
- Hotkeys don't conflict with screen reader shortcuts
- Color is never the only signal — every green/red state also has a sign (+/-) or a shape (shield, arrow)
- Reduced-motion media query respected: all motion (including the signature moments) reduces to instant transitions

### 14.4 Dark mode only

No light mode toggle. The design is optimized for one palette; shipping two half-optimizes both.

### 14.5 Performance

- Landing page LCP under 2.5s on a 3G Fast connection
- Dashboard initial render under 2s on a laptop
- No layout shift on NAV updates (this is why tabular-nums matters)
- Sunburst viz renders at 60fps on its update animations

---

## 15. Telegram bot

Minimal, text-forward. Not rich cards, not inline buttons. The bot's job is to fire short, informative pings during the demo (and during real operation).

**Message style:**

```
⚡ Allocation complete
$300 → MomentumKite-A
$250 → MeanRevBase-B
$250 → MomentumArb-C
$200 → YieldRotationArb-D
Total deployed: $1,000
```

```
⚠️ Drawdown breach
MomentumKite-A defunded at -15.2%
Capital reallocating to MeanRevArb-E...
```

```
✓ Rebalance complete
Net change: +$12.40 over 7 days
Current NAV: $1,012.40
```

**Rules:**
- Each message under 200 characters
- One event per message — never batch unrelated events
- Emoji is allowed here but used with restraint — status markers only (⚡ for activity, ⚠️ for alerts, ✓ for confirmations)
- No bot personality, no "hi!" greetings, no reaction prompts
- All numbers formatted identically to the web app (tabular-friendly even in a text channel)
- Trade links point to the chain explorer (Kitescan on Kite; BaseScan / Arbiscan on Phase 5 chains)

This is a trader's channel, not a community chat.

---

## 16. What I need back from you

Deliverables, in priority order:

1. **Visual direction review (1-2 days after brief).** Show me 2-3 mood boards showing your interpretation of the aesthetic direction. Confirm we're aligned before you spend time on component design.

2. **Component system (week 1).** Typography specimen, color token set, core components (button, input, card, table, modal, badge, nav). Render as a Figma page or a static style guide document. Decisions finalized.

3. **High-priority screen designs (weeks 1-2).** In order: `/dashboard`, `/judge`, `/onboard`, `/`. These carry the most weight in the hackathon evaluation.

4. **Medium-priority screens (week 2-3).** `/strategies`, `/strategies/[id]`, `/allocators`, `/audit/[strategy]`.

5. **Motion specs (week 2-3).** For the three signature moments. Can be Figma prototype, After Effects, Lottie, or a written description with timing. Written is fine — the dev implements from the description.

6. **Responsive breakpoints (week 3).** Tablet and mobile treatments for core views only.

7. **Component handoff notes.** For the frontend dev — CSS/Tailwind tokens, component structure notes, any non-obvious interaction behavior.

**What I'll give you in return:**

- `SPEC.md` — the complete product spec, source of truth for behavior
- Access to the live subgraph and backend once they exist, so live data can drive the designs
- Fast feedback turnaround — under 24 hours on any open design question

**Open questions I'd flag for you early:**

- The sunburst's exact behavior on rebalance vs defund — do they animate differently?
- The "Official Reference" badge treatment for Sentinel and Helix — should this be visually identical or subtly differentiated?
- The type pairing (you're deciding) — my only constraint is "not Inter, not Roboto, treat the numerics as first-class"
- The landing page's stats band — should it be one line of numbers, or a more prominent visual treatment?

Use your judgment. If you're unsure whether something is in-scope for you to decide, assume it is and show me. Easier to dial back than to fill in a blank.

---

*Design brief v1. Companion to `SPEC.md`. Updates to either document should be reflected in both.*
