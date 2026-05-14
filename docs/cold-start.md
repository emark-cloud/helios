# Helios cold-start — judge's 5-minute reproduce path

> **For judges + first-time evaluators.** You cloned the repo. You
> want to confirm Helios's claims hold up — that real trades carry
> ZK proofs, that allocations land on three chains, that reputation
> stitches across via LayerZero — **without** standing up the full
> stack locally.
>
> This page is the fastest path to that confirmation. Total time:
> 5 minutes including reading.

---

## TL;DR

| What you want to confirm | How (under 1 min each) |
|---|---|
| Real strategies with reputation scores | Open `https://helios.market/strategies` |
| Real ZK-attested trades on Kite | Open `https://helios.market/judge`, scroll to "Recent attested trades" |
| Verify a proof yourself | `node scripts/verify-trade.js <tx-hash>` from a clone |
| Capital really moves cross-chain | Visit any `RemoteAllocationSent` tx on Kitescan + its LZScan trace |
| Reputation really crosses chains | LZ GUID `0x24fd5344…` (Base → Kite) |

If all five check out, the protocol works as described. Everything
below is the detail.

---

## Prerequisites

For the CLI verify path:

- **Node 20+** (the only hard dependency for verify-trade.js).
- A clone of this repo: `git clone https://github.com/emark-cloud/helios && cd helios`.

That's it. You do not need `pnpm`, `uv`, `forge`, or `docker` to
re-verify any on-chain trade. The full stack is documented in
`README.md` if you want to stand it up locally, but for evaluation
the live deploy plus a single Node script are sufficient.

---

## Step 1 — Tour the live surfaces (90 s)

The frontend is on Vercel. Five pages that matter:

| Page | What it shows |
|---|---|
| `/` | Landing page with live LandingStatsBand (strategies online + total NAV) |
| `/strategies` | All 12 strategies across 3 chains; sortable by score, filterable by class + chain |
| `/judge` | This page's live equivalent: address tables, recent trades, verify-trade command, 5-step eval checklist |
| `/audit/strategy/<id>` | Per-strategy reputation breakdown (§8.2 components broken out) |
| `/dashboard` | What a logged-in user sees — capital cascade, allocations, activity rail |

The dashboard requires a Passport wallet to populate. The other
four pages render against Goldsky's public read endpoints — no
login required.

---

## Step 2 — Verify an attested trade (60 s)

From a clone:

```bash
# Pick any recent TradeAttested tx from /judge or from the Goldsky
# query in step 3, then:
node scripts/verify-trade.js <tx-hash>
```

What this does:

1. Fetches the transaction receipt from Kite RPC.
2. Decodes the Groth16 proof bytes from the `executeWithProof`
   calldata.
3. Reconstructs the public-input array (`oracle_root`,
   `params_hash`, `asset_universe_hash`, `action_kind`,
   `decimals_in`, `decimals_out`, `declared_class`, …).
4. Runs the verifier locally — same verifying key the on-chain
   `TradeAttestationVerifier` uses.
5. Prints `PROOF VALID ✓` (exit 0) or the reason it failed
   (exit 1).

Run time ~ 5–10 s. No live service required beyond a Kite RPC
endpoint (defaults to `https://rpc-testnet.gokite.ai`).

---

## Step 3 — Query the subgraph directly (60 s)

The protocol's state is indexed by Goldsky. Public read endpoint
(no API key needed):

```
https://api.goldsky.com/api/public/project_cmodpmbv1pkd70127d9g741ek/subgraphs/helios/v0.9.0/gn
```

Example query for the eight `TradeAttested` events fired by mr.kite
on 2026-05-12 — the canonical proof set:

```graphql
{
  tradeAttesteds(
    where: { strategyVault: "0x1717640c4f9cd9f84b028bc8dfdcea3fb0572c6a" }
    orderBy: blockNumber
    orderDirection: desc
    first: 10
  ) {
    blockNumber
    transactionHash
    declaredClass
    publicInputs
  }
}
```

Two sibling subgraphs cover the execution chains:

- Base Sepolia: `helios-base/v0.8.0`
- Arbitrum Sepolia: `helios-arbitrum/v0.8.0`

---

## Step 4 — Cross-chain (90 s)

Helios moves both capital and reputation across chains via
LayerZero V2.

**Capital, Kite → Base.** Three real hops on 2026-05-14:

- mr.base — Kite tx `0x6ef584a1…` → Base `0x8b375617…` credit
  `650_331` mUSDC (6-dec)
- mom.base — Kite tx `0xfee792dc…` → Base `0x9e14299e…` credit
  `650_331` mUSDC
- yr.arb — Kite tx `0xcda2e6bd…` → Arb `0x516f23b9…` credit
  `650_331` mUSDC

Verify on LZScan: paste any tx hash into `https://testnet.layerzeroscan.com/tx/<tx>`.

**Reputation, Base → Kite.** GUID `0x24fd5344…` moved
SR-v3 `currentReputation` from 0 → 750 for one strategy in a
single LZ V2 hop. Evidence on Kitescan:
`ReputationAnchor V2-bis (0x2b6c5f36…)` →
`postCrossChainUpdate` event.

---

## Step 5 — The mechanism, top-down (60 s)

If you have one more minute, read these three sections of
`Helios.md`:

- **§3 — The breakthrough.** Why on-chain class enforcement via ZK
  is the unlocking primitive, not just a nice-to-have.
- **§6.5 — `StrategyVault.executeWithProof`.** The single function
  that enforces every claim in this document.
- **§14 — Demo scenario.** What the demo video shows + why
  scenario-mode is real-mechanism-not-cheating.

If you have *another* minute, read `docs/phase6-acceptance.md` for
the empirical evidence trail (every claim above traced to an
on-chain artifact).

---

## "I want to deploy my own ___"

| Goal | Where to start |
|---|---|
| Ship a competing strategy class | [`docs/operator-guide.md`](./operator-guide.md) |
| Ship a competing allocator | [`docs/allocator-guide.md`](./allocator-guide.md) |
| Understand the ZK circuits | [`docs/circuit-specs.md`](./circuit-specs.md) |
| Audit the reputation math | [`docs/reputation-math.md`](./reputation-math.md) |
| Review the threat model | [`docs/threat-model.md`](./threat-model.md) |

---

## Known omissions from the public clone

- `TODO.md` and `DESIGN.md` are gitignored (local-only planning
  docs). `CLAUDE.md` still references them — those references are
  broken from a fresh clone. Everything load-bearing for evaluation
  is in `Helios.md` + the documents under `docs/`.
- Phase planning docs (`phase5-xchain-verification.md`,
  `phase6-plan.md`, `phase6-realprice-plan.md`,
  `post-demo-tav-restore.md`) were retired into
  `docs/phase6-acceptance.md` on 2026-05-14. If you find references
  to them anywhere, prefer `phase6-acceptance.md`.

---

## Help

- Verify-trade.js failures: open an issue with the tx hash + the
  full output.
- Frontend bugs: include the page URL + browser console output.
- Anything else: `eakinleye97dami@gmail.com`.
