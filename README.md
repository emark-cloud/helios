# Helios

**A programmatic capital market for AI trading agents on Kite.**

Users sign one meta-strategy. An allocator agent autonomously routes
their capital across competing strategy agents. Every trade carries
a Groth16 ZK proof binding it to the strategy's declared class.
Reputation accrues from realized, attested performance and flows
across chains via LayerZero.

> Built for the Kite AI Global Hackathon 2026 — Agentic Trading &
> Portfolio Management track.

## The problem

If you want to deploy capital with an AI trading agent today, you
have two bad options:

1. **Run one yourself.** Hard, technically risky, requires constant
   operational oversight. Most users can't.
2. **Hand custody to a centralized AI fund service.** You trust the
   operator's code, infra, and intentions. No verifiable
   performance, no recourse if they misbehave.

There is no middle ground — no market mechanism that forces strategy
agents to perform, lets capital flow programmatically to good ones
and away from bad ones without a human middleman, cryptographically
constrains what an agent can do so a compromised agent can't drain
funds, and makes reputation portable across chains.

## The solution

A user approves **one** meta-strategy — for example, *"up to $10,000
across momentum strategies trading BTC/ETH/SOL, max 30% per
strategy, defund on 15% drawdown."* From that single Kite Passport
approval, an **Allocator Agent** queries the on-chain Strategy
Registry, ranks eligible strategies by reputation, and delegates
capital. Each **Strategy Agent** trades on whichever chain has the
best venue, attaching a Groth16 proof binding the trade to its
declared class. A momentum agent literally cannot execute a yield
rotation and have it count.

## Architecture

```text
  User
   │ 1 signature (Passport, batched userOp)
   ▼
  UserVault — capital + meta-strategy bounds
   │ delegateToAllocator
   ▼
  AllocatorVault (Sentinel) — routes per rank
   │ allocateToStrategy / allocateToRemoteStrategyBatch
   ▼
  StrategyVault — holds capital, executes trades
   │ executeWithProof(Groth16 π)
   ▼
  TradeAttestationVerifier — class check
   │ emit TradeAttested
   ▼
  Goldsky → Reputation Engine → ReputationAnchor
                                  ▲
                LayerZero V2 ← cross-chain reputation
                LayerZero V2 → cross-chain capital (OFT)
```

**A trade in five steps.** (1) The user signs once via Kite Passport
— a batched userOp deposits USDC, sets the meta-strategy, and
delegates to Sentinel. (2) Sentinel ticks every 60 s, ranks all live
strategies by realized performance + stake, and allocates capital;
same-chain via `allocateToStrategy`, cross-chain via a batched
LayerZero V2 OFT send. (3) Each Strategy Agent observes price + its
declared signal, builds a Groth16 proof of class compliance, and
submits `executeWithProof`. (4) The on-chain verifier rejects any
trade that doesn't satisfy the class circuit — bad trades cannot
land. (5) Reputation derives from realized, attested P&L, computed
off-chain by the Reputation Engine, signed, and posted on-chain;
LayerZero V2 carries updates from execution chains back to Kite.

## Agent taxonomy

Two roles, both fully autonomous on-chain:

- **Allocator agent** (Sentinel) — hybrid **utility-based +
  model-based reflex** with a hard goal envelope. Each 60 s tick
  scores live strategies on `f(reputation, stake, capacity,
  freshness)` and allocates by rank, inside the user's
  meta-strategy constraints. Third parties ship competing
  allocators via `helios-allocator-sdk`.
- **Strategy agent** (one per vault) — **model-based reflex** in
  the reference implementations: a rolling price window plus a
  fixed rule per class (momentum return, mean-reversion z-score,
  yield-rotation Δ). The protocol is indifferent to the signal
  source — rules, RL, or LLM all work — as long as each trade
  satisfies the class circuit. The ZK class binding is what
  defines an agent's type from the protocol's point of view.

Mapped onto the finance multi-agent split: Sentinel is a
**portfolio-construction agent with execution authority**;
strategy agents are **trader agents with class-bound autonomy**.
Helios's contribution is removing the fiduciary human-in-the-loop
typical at both layers, replacing it with the meta-strategy
commitment + ZK class enforcement + auto-defund.

## What works today

Live as of `v1` (2026-05-14):

- **12 strategy vaults** across three chains: 9 on Kite testnet
  (momentum + mean-reversion + yield-rotation × 3 variants each), 2
  on Base Sepolia (mom.base + mr.base on Uniswap V3), 1 on Arbitrum
  Sepolia (yr.arb on an Aave-V3-shaped venue).
- **Real ZK-attested trades.** First 8 autonomous `TradeAttested`
  events fired from mr.kite on 2026-05-12. Each carries a 16-PI
  Groth16 proof, on-chain class-verified before settlement.
- **Real cross-chain capital flow.** 3 LZ V2 hops delivered on
  2026-05-14 (mom.base, mr.base, yr.arb each credited with
  0.650331 mUSDC on destination, zero parked on BridgeReceivers).
- **Real cross-chain reputation.** A Base→Kite update via LayerZero
  V2 moved `currentReputation` 0 → 750 for one strategy in a single
  hop.
- **Deployed end-to-end.** Frontend on Vercel; sentinel + reputation
  + oracle services on a Servarica Montreal VPS; Goldsky subgraphs
  `helios/v0.9.0` + `helios-base/v0.8.0` + `helios-arbitrum/v0.8.0`
  index all three chains.
- **LLM strategy reference.** `reference-strategies/llm_momentum_v1/`
  ships a Claude-driven `momentum_v1` strategy — the model decides
  LONG/EXIT/HOLD per bar via Anthropic tool use; the on-chain
  `params_hash` enforces the operator's declared bounds. Scaffold
  your own with `helios scaffold-strategy llm_momentum_v1 --name <NAME>`.

Full empirical evidence trail (every claim → on-chain artifact):
[`docs/helios-v1-acceptance.md`](./docs/helios-v1-acceptance.md).

## Current limitations & mitigations

**LayerZero V2 cross-chain cost.** Each `OFT.send` on Kite testnet
costs 1.0 KITE (~$0.50–$2 mainnet equivalent), driven by the LZ
DVN fee floor + executor base fee, not by gas. A 3-candidate
cold-start cross-chain broadcast cost 3.2 KITE before optimization.

- *Shipped in `v1`.* Tier 1 (threshold gate skips dust ops,
  flush cadence amortizes re-fires) + Tier 2
  (`allocateToRemoteStrategyBatch` collapses same-destination
  strategies into one OFT send) drops the same broadcast to
  ~2.2 KITE.
- *Roadmapped.* Tier 3 folds the receiver into the OFT adapter's
  `_credit` hook (saves another ~30–40 % per hop); Tier 4
  aggregates multiple users into one OFT send per (dst chain,
  strategy), linear savings with concurrent user count. Full
  design:
  [`docs/cross-chain-cost-roadmap.md`](./docs/cross-chain-cost-roadmap.md).

**Centralized v1 trust surfaces.** Per
[`docs/threat-model.md`](./docs/threat-model.md) +
[`Helios.md §15.1`](./Helios.md):

- *Reputation signer.* Single key in v1; v2 migrates to 5-of-9
  multi-sig; v3 makes the computation itself ZK-attested.
- *Price oracle.* Helios-operated in v1; a Pyth / Chainlink
  adapter is planned for v2. The auto-defund path reads
  `StrategyVault.navOf()` rather than the oracle, so a compromised
  oracle can falsify proofs but cannot suppress a defund.
- *Yield-market allowlist.* Curated by the Helios multi-sig in v1;
  v2 moves to per-class governance.

## Roadmap

Helios is built as v1 of a real protocol

**Phase 1 (next 1–3 months).** Production trusted-setup ceremony,
multi-sig reputation signer, AllocatorSDK adoption push (5–10
third-party allocators), permissionless strategy-class registration
with circuit-submission gating, Chainlink-backed price oracle
adapter, independent smart-contract audit.

**Phase 2 (months 4–6).** Mainnet deployment on Kite L1, USDT +
USDG stablecoin support, capacity-adjusted Sharpe in the reputation
formula, slashing-dispute mechanism, Echidna property fuzz suites,
Hyperliquid-backed `basis_v1` strategy class.

**Phase 3 (months 7–12).** ZK-attested reputation (eliminates the
signer entirely), insurance fund seeded from protocol fees,
expansion to Optimism / Polygon / Avalanche, DAO governance.

Full detail in [`Helios.md §17`](./Helios.md).

## For judges

Five-minute reproduce path, no VPS required:
[`docs/cold-start.md`](./docs/cold-start.md). Or click straight to
the live eval page: [`/judge`](https://helios-frontend-steel.vercel.app/judge) — it
lists deployed addresses, recent attested trades, and the
verify-trade command inline.

## Repo map

| Path | Purpose |
|---|---|
| [`contracts/`](./contracts) | Foundry project (Solidity, tests, deploy scripts, deployments JSON) |
| [`circuits/`](./circuits) | Circom circuits + snarkjs build output |
| [`packages/strategy-sdk/`](./packages/strategy-sdk) | `helios-strategy-sdk` PyPI package |
| [`packages/allocator-sdk/`](./packages/allocator-sdk) | `helios-allocator-sdk` PyPI package |
| [`packages/helios-cli/`](./packages/helios-cli) | `helios-trader-cli` PyPI CLI |
| [`services/sentinel/`](./services/sentinel) | Reference allocator (FastAPI) |
| [`services/reputation/`](./services/reputation) | Reputation engine — Goldsky → signed scores → on-chain |
| [`services/prover/`](./services/prover) | Groth16 proof-generation HTTP wrapper around snarkjs |
| [`services/oracle/`](./services/oracle) | Helios-operated price + yield oracle |
| [`reference-strategies/`](./reference-strategies) | Reference strategy implementations (deterministic + LLM-driven) |
| [`subgraph/`](./subgraph) | Goldsky subgraph manifest, schema, mappings |
| [`frontend/`](./frontend) | Next.js 14 App Router frontend |
| [`scripts/`](./scripts) | E2E scenarios, verify-trade.js, preflight + measurement scripts |
| [`docs/`](./docs) | Long-form docs (operator-guide, allocator-guide, threat-model, …) |

## Documentation

- **Spec** (read this if you want the depth) → [`Helios.md`](./Helios.md)
- **Helios v1 acceptance** (the live-evidence trail) → [`docs/helios-v1-acceptance.md`](./docs/helios-v1-acceptance.md)
- **Cold-start one-pager** (5-min reproduce) → [`docs/cold-start.md`](./docs/cold-start.md)
- **Operator guide** (ship a strategy) → [`docs/operator-guide.md`](./docs/operator-guide.md)
- **Allocator guide** (ship a competing allocator) → [`docs/allocator-guide.md`](./docs/allocator-guide.md)
- **Threat model** → [`docs/threat-model.md`](./docs/threat-model.md)

## Quick start (developers)

Prerequisites: Node 20+, pnpm 9+, Python 3.11+,
[`uv`](https://docs.astral.sh/uv/), Foundry
(`curl -L https://foundry.paradigm.xyz | bash`), Circom 2.1.9+,
Docker.

```bash
pnpm install
uv sync
forge install --root contracts

# Boot local stack
pnpm dev

# Per-surface
forge test -vv                        # contracts (from contracts/)
pnpm --filter frontend dev            # frontend at :3000
python -m services.sentinel           # allocator
cd circuits && make momentum_v1       # circuit build
```

Copy `.env.example` → `.env` and fill in at least `KITE_RPC_URL`,
`DATABASE_URL`, `KITE_PASSPORT_SESSION_ID`. VPS deployment scripts
and operational defaults (rate limits, Nginx config, PM2 units)
live in [`deploy/`](./deploy).


## License

MIT. See [`LICENSE`](./LICENSE).
