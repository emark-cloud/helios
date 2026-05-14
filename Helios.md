# Helios — MVP Specification

**A programmatic capital market for AI trading agents on Kite, with ZK-attested execution and cross-chain reputation.**

> Version 0.1 — submitted for the Kite AI Global Hackathon 2026, Agentic Trading & Portfolio Management track.

---

## Table of contents

1. [Mission and product narrative](#1-mission-and-product-narrative)
2. [Why Helios fits the Kite hackathon thesis](#2-why-helios-fits-the-kite-hackathon-thesis)
3. [Glossary of core concepts](#3-glossary-of-core-concepts)
4. [System overview and architecture](#4-system-overview-and-architecture)
5. [User personas and journeys](#5-user-personas-and-journeys)
6. [On-chain components — smart contracts](#6-on-chain-components--smart-contracts)
7. [Off-chain components — services](#7-off-chain-components--services)
8. [The reputation engine](#8-the-reputation-engine)
9. [The ZK strategy attestation system](#9-the-zk-strategy-attestation-system)
10. [The Strategy Agent SDK](#10-the-strategy-agent-sdk)
11. [The Allocator Agent](#11-the-allocator-agent)
12. [Cross-chain architecture](#12-cross-chain-architecture)
13. [Frontend and event surfaces](#13-frontend-and-event-surfaces)
14. [Demo scenario and stagecraft](#14-demo-scenario-and-stagecraft)
15. [Security, trust, and threat model](#15-security-trust-and-threat-model)
16. [Out-of-scope for MVP](#16-out-of-scope-for-mvp)
17. [Post-hackathon roadmap](#17-post-hackathon-roadmap)
18. [Repository layout](#18-repository-layout)
19. [Judge quick-evaluation guide](#19-judge-quick-evaluation-guide)

---

## 1. Mission and product narrative

### 1.1 The one-liner

Helios is **a programmatic capital market for AI trading agents on Kite**. Users delegate funds to allocator agents that auto-route capital to top-performing strategy agents and auto-defund failing ones — with every trade cryptographically proven to match the strategy's declared class, and reputation that flows across chains.

### 1.2 The problem

Today, if you want to deploy capital with an AI trading agent, you have two bad options:

1. **Run one yourself.** Hard, technically risky, requires constant operational oversight. Most users can't.
2. **Hand custody to a centralized AI fund service.** Scary — you trust the operator's code, infra, and intentions. No verifiable performance, no recourse if they misbehave.

There is no middle ground. There's no market mechanism that:

- Forces strategy agents to actually perform (instead of just marketing themselves)
- Lets capital flow programmatically to good agents and away from bad ones, without a human middleman
- Cryptographically constrains what an agent can do, so a compromised agent can't drain funds
- Lets reputation be portable across chains, so a strategy that built a track record on Base can attract capital from Kite users

Existing AI trading products are either fully custodial or fully self-hosted. Neither matches the agentic-economy thesis: **autonomous agents transacting under cryptographic constraints, with capital flowing on the basis of verifiable performance, not promises.**

### 1.3 The Helios solution

A user approves **one** meta-strategy. For example:

> *"Allocate up to $10,000 across momentum strategies trading BTC/ETH/SOL/BNB. Maximum 30% in any single strategy, max 5 strategies total. Only consider strategies with a 30-day Sharpe > 1.5 and stake at risk > $5,000, with 10% reserved as a bootstrap exploration pool for new strategies under 50 attested trades. Rebalance weekly. If any strategy hits 15% drawdown from its high-water mark on my capital, defund immediately. Maximum performance fee: 25%."*

From that single passkey approval — a Kite Passport login that funds and configures the user's vault — a cascade unfolds autonomously:

1. The user's **Allocator Agent** queries the **Strategy Registry**, ranks eligible strategies by reputation, and delegates capital portions via on-chain allocations gated by the meta-strategy.
2. **Strategy Agents** receive their allocations and begin trading on whichever chain has the best venue (Kite, Base, or Arbitrum). Every trade comes with a **Groth16 proof** binding the executed calldata to the strategy's declared class.
3. The **Reputation Engine**, indexed by Goldsky, continuously updates strategy scores based on realized, ZK-attested P&L.
4. When a strategy hits its drawdown threshold, the allocator **automatically defunds it** and reroutes the capital to the next-best-ranked eligible strategy.
5. Performance fees flow through **x402** — strategy agents earn from allocators only on realized profit above the high-water mark; allocators earn from users on the same basis.
6. **LayerZero** carries reputation deltas back to Kite when strategies execute on other chains, keeping the registry canonical.

The user approved once. Everything else happens autonomously, under cryptographic constraints, with every action auditable on-chain.

### 1.4 Why this is the right shape

This is not a trading bot. It's not a portfolio dashboard. It's not an AI fund service.

Helios is **market infrastructure for the agentic economy** — the missing layer that makes AI trading agents a category instead of a collection of one-off products. The mechanism (reputation + auto-defund + ZK attestation + x402 fees) is the IP. The strategy agents are interchangeable participants. The users are end-consumers of a market, not customers of a service.

Three shifts make Helios different from anything currently shipping:

1. **Capital allocation is itself an agentic action.** The allocator is an autonomous agent following programmatic constraints. Existing fund-of-funds require a human portfolio manager. Helios doesn't.
2. **Reputation is computed from cryptographically attested behavior.** Every trade carries a ZK proof binding it to the strategy's declared class — a "momentum" agent literally cannot be credited with reputation for executing arbitrage, even by mistake or attack.
3. **Capital flows automatically.** No discretionary human decision. The user sets policy; the system enforces it. A failing strategy gets defunded the instant it breaches the threshold, not after a quarterly review.

---

## 2. Why Helios fits the Kite hackathon thesis

The Kite AI Global Hackathon brief is unusually specific:

> *Build agents that **operate and settle** on Kite chain. Agent-first solutions instead of human-first. Show as much autonomous execution as possible, end to end.*

Helios maps to this brief at every level:

| Hackathon emphasis | Helios mapping |
|---|---|
| **Agent-first, not human-first** | The user approves one meta-strategy and never touches the system again. The allocator agent makes all subsequent decisions; strategy agents execute; reputation engine scores; defunds happen autonomously. |
| **End-to-end autonomous execution** | A single passkey approval triggers: capital cascade → strategy execution → ZK proof generation → on-chain verification → reputation update → fee settlement → potential defund and reallocation. Every step is automated. |
| **Use Kite's identity, payment, governance, verification** | Identity: Passport-issued ERC-4337 smart account (`@gokite-network/auth` + `gokite-aa-sdk`) with on-chain allocator delegation. Payment: x402 performance fees + state-channel micropayments. Governance: meta-strategy bounds enforced in Solidity on every allocator call. Verification: ZK proofs anchored on-chain. |
| **Agentic Trading & Portfolio Management track** | Direct hit on three of the track's bullet points: trading agents (the strategy agents), portfolio agents and liquidation defense (the allocator's drawdown enforcement), reputation/scoring/capital delegation agents (the entire mechanism). |
| **Long-term aligned, beyond the hackathon** | Helios is a real market mechanism. Coinbase Ventures (lead hackathon partner) explicitly invests in agent-economy infrastructure; this is a category-level product, not a feature. |
| **Cross-chain** | Strategies trade on Base/Arbitrum where venues are deeper; reputation flows back via LayerZero. Kite is the canonical identity and accounting layer. |

The hackathon's stated thesis — *"AI agents should not just talk. They should own assets, earn revenue, and participate in onchain economies"* — describes Helios literally. Strategy agents own balances, earn performance fees, and participate in a market for capital allocation. Allocators are agents whose entire job is interacting with other agents.

### 2.1 Use of Kite's uniquely uncopiable primitives

Kite has three architectural primitives that no other chain offers in combination. Helios uses all three as load-bearing, not cosmetic.

**1. Passport-issued ERC-4337 identity (User → AA wallet → on-chain allocator delegation).** Helios uses Kite Passport's embeddable widget (`@gokite-network/auth`, Particle-MPC backed) to issue a smart-account wallet for the user on first login. From that wallet, the user calls `UserVault.setMetaStrategy` and `UserVault.delegateToAllocator`; the allocator's authority is then a Solidity-enforced ACL keyed on its registered EOA. Compromising the allocator's key stays bounded by the meta-strategy (every allocation reverts on out-of-bounds amount or asset); the user's session is non-custodial via Particle's MPC and revocable at any time. This is a deliberate softening of the v0 spec's "BIP-32 hierarchical, root keys never leave the enclave" claim — the actual `gokite-aa-sdk` exposes ERC-4337 + paymaster, not session-key delegation, so we enforce the cascade in Solidity rather than in identity-derivation.

**2. ERC-4337 smart-account spending bounds + paymaster.** The AA wallet supports batched userOps and ERC-20 paymaster sponsorship. Helios uses both: onboarding deposits batch `USDC.approve(UserVault, amount)` + `UserVault.deposit(amount)` into a single userOp, and strategy operators submit gasless `executeWithProof` userOps via paymaster sponsorship. Conditional triggers like "if strategy drawdown > 15%, freeze trades and trigger defund" live in `AllocatorVault` Solidity, not in the AA wallet itself.

**3. x402 micropayments and state channels.** Performance fees flow through x402 — this is the protocol-level fee mechanism in v1, settled when the Allocator crystallizes performance fees above HWM. Strategy agents subscribe to data providers (price oracles, signal feeds) via x402 sessions issued through the same Passport wallet. Where applicable, allocator-to-strategy quote and rebalance signals can use state channels for sub-cent latency. Wrapping the prover, oracle, and audit endpoints as x402-paid services (so the Allocator literally pays for proofs through the Pieverse facilitator during the live demo) is a deferred polish track — see §16 and post-hackathon Phase 1 in §17.

---

## 3. Glossary of core concepts

| Term | Definition |
|---|---|
| **User** | The human who deposits capital and approves a meta-strategy via a Passport passkey login. Holds root authority over their AA wallet. |
| **Meta-strategy** | The user's approved declaration of allocation policy: capital cap, asset universe, allowed strategy classes, max per-strategy concentration, drawdown thresholds, max acceptable fee rate, rebalancing cadence. Stored on-chain in `UserVault.userMetaStrategies`; the AA wallet is the only address authorized to write it. |
| **Allocator Agent** | An autonomous agent that reads a user's meta-strategy and routes their capital across strategies. Holds delegated authority from the user. Earns a performance fee on the user's net realized profit above the user's high-water mark. |
| **Strategy Agent** | An autonomous trading agent of a declared class (e.g. momentum, mean-reversion, yield-rotation). Receives allocations from one or more allocators. Executes trades on Kite or other chains. Submits ZK proofs of every trade. Earns performance fees on realized profit per allocation. |
| **Strategy Class** | A formal declaration of what kind of trades a strategy agent is permitted to make. Encoded as a circuit-checkable specification. Examples: `momentum_v1` (long when N-period return > threshold, short or flat otherwise), `mean_reversion_v1`, `yield_rotation_v1`. |
| **Helios Sentinel** | The primary branded reference allocator shipped by the Helios team. Ships a deliberately simple ranking function that serves as the baseline competing allocators aim to beat. The name is a reserved brand in `AllocatorRegistry`. |
| **Helios Helix** | The second branded reference allocator. Ships a more sophisticated ranking function (correlation-aware, regime-adaptive). Its primary load-bearing purpose is validating that the AllocatorSDK is real — Helix was built from the ground-up on the SDK. Also a reserved brand. |
| **AllocatorSDK** | Public Python package that lets anyone deploy a competing allocator. A v1 deliverable. Third-party allocators built on this SDK can register on `AllocatorRegistry` under any non-reserved name and compete with Sentinel and Helix for user capital. |
| **Strategy Manifest** | The on-chain record describing a strategy agent: declared class, asset universe, max capacity, fee rate, stake at risk, operator address. |
| **Stake at Risk** | Capital posted by a strategy operator that gets slashed on rule violations (invalid proof, out-of-bounds trade). Reputation calculations weight strategies by stake — higher stake means more skin in the game. |
| **Strategy Registry** | The on-chain contract on Kite that holds all strategy manifests, reputation scores, and stake balances. |
| **Reputation Score** | A multi-factor on-chain score derived from a strategy's realized P&L history, drawdown, stake size, and proof validity rate. Computed by the Reputation Engine, indexed by Goldsky. |
| **High-Water Mark (HWM)** | The peak NAV a particular allocation has ever reached. Performance fees are charged only on profit above HWM. Tracked per (allocator, strategy, user) tuple. |
| **Trade Attestation** | A Groth16 ZK proof that a specific executed trade satisfies the strategy class's declared invariants (correct asset, correct direction, within size bounds, within slippage bounds, within time window). |
| **Auto-Defund** | The mechanism by which the allocator pulls capital from a strategy that has breached the user's drawdown threshold, without human intervention. |
| **Cross-Chain Reputation** | Reputation updates from strategies executing on Base or Arbitrum get propagated back to the Kite registry via LayerZero OApp messages. |
| **Verified Set** | The subset of strategy agents and allocators that the Helios team operates on its VPS for the demo. Public SDK and Docker images allow anyone to deploy their own. |

---

## 4. System overview and architecture

### 4.1 High-level architecture

```
                        ┌─────────────────────────────────────┐
                        │            USER (Human)             │
                        │   Approves meta-strategy via Kite   │
                        │   Passport (passkey). AA wallet     │
                        │   holds root authority.             │
                        └──────────────┬──────────────────────┘
                                       │ 1 passkey approval
                                       ▼
                  ┌────────────────────────────────────────┐
                  │       USER VAULT (Kite, AA SDK)        │
                  │  Holds capital. Enforces meta-strategy │
                  │  constraints. Authorizes an Allocator   │
                  │  Agent (on-chain ACL).                 │
                  └─────────────────┬──────────────────────┘
                                    │
                                    ▼
                  ┌────────────────────────────────────────┐
                  │      ALLOCATOR AGENT (off-chain)       │
                  │  Reads meta-strategy. Queries          │
                  │  Strategy Registry (via Goldsky).      │
                  │  Ranks strategies. Delegates capital.  │
                  │  Monitors drawdowns. Triggers defund.  │
                  └────┬──────────────┬──────────────┬─────┘
                       │              │              │
                       ▼              ▼              ▼
               ┌──────────────┐┌──────────────┐┌──────────────┐
               │  Strategy A  ││  Strategy B  ││  Strategy C  │
               │  (momentum)  ││  (mean-rev)  ││  (momentum)  │
               │  on Kite     ││  on Base     ││  on Arbitrum │
               └──────┬───────┘└──────┬───────┘└──────┬───────┘
                      │ trade         │ trade         │ trade
                      ▼               ▼               ▼
                 ┌────────────────────────────────────┐
                 │   Each trade: Groth16 ZK proof     │
                 │   binding executed calldata to     │
                 │   declared strategy class.         │
                 └─────────────────┬──────────────────┘
                                   │
                                   ▼
                 ┌────────────────────────────────────┐
                 │   ON-CHAIN VERIFIER (per chain)    │
                 │   Verifies proof before settlement.│
                 │   Emits TradeAttested event.       │
                 └─────────────────┬──────────────────┘
                                   │
                                   ▼
                 ┌────────────────────────────────────┐
                 │   GOLDSKY INDEXER                  │
                 │   Indexes attested trades, P&L,    │
                 │   stake events, reputation deltas. │
                 └─────────────────┬──────────────────┘
                                   │
                                   ▼
                 ┌────────────────────────────────────┐
                 │   REPUTATION ENGINE                │
                 │   Computes rolling Sharpe, max DD, │
                 │   stake-weighted score. Updates    │
                 │   Strategy Registry on Kite.       │
                 └────────────────────────────────────┘

       (Cross-chain reputation messages flow Base → Kite,
        Arbitrum → Kite via LayerZero OApp.)
```

### 4.2 The seven-layer stack

| Layer | What lives here | Trust model |
|---|---|---|
| **L0: Settlement** | Kite L1 (canonical), Base, Arbitrum (execution venues) | Inherits chain security |
| **L1: Identity** | Kite Passport (Particle-MPC EOA → ERC-4337 smart account → on-chain allocator/strategy ACL) | Non-custodial via Particle MPC; cascade authority enforced in Solidity rather than in key derivation |
| **L2: Capital custody** | UserVault, AllocatorVault, StrategyVault (all AA SDK contracts) | Programmable spending rules, ZK-gated execution |
| **L3: Strategy registry** | StrategyRegistry contract on Kite | Permissionless registration, stake-gated participation |
| **L4: Verification** | TradeAttestationVerifier (per chain), Groth16 verifier contracts | Mathematical — invalid proofs cannot pass |
| **L5: Reputation** | ReputationEngine (off-chain compute, on-chain anchoring) | Deterministic given attested trade history |
| **L6: Coordination** | Allocator agents, strategy agents, off-chain services | Hosted by anyone; on-chain logic enforces constraints |
| **L7: User surface** | Web app + activity rail, REST/WebSocket API (Telegram bot deferred — see §16) | UX layer; no security responsibility |

### 4.3 The data flow lifecycle

A complete cycle from user approval to first reallocation:

```
T+0s      User approves meta-strategy via Kite Passport (passkey)
T+1s      UserVault deployed; capital deposited; AllocatorAgent assigned
T+5s      Allocator queries Goldsky for top-N eligible strategies
T+10s     Allocator computes target allocation; issues sub-delegations
T+15s     StrategyVaults receive capital; strategy agents activate
T+20s     Strategy agents begin trading; each trade generates ZK proof
T+30s     First trades verified on-chain; TradeAttested events emitted
T+45s     Goldsky indexes events; Reputation Engine recomputes scores
T+60s     User dashboard updates with first NAV reading

(continuous from T+60s onward)

Every 5 min:    Allocator polls strategy NAVs, checks drawdown thresholds
Every 1 hour:   Reputation Engine emits ranking deltas; Allocator considers reallocation
On drawdown breach: Allocator immediately defunds breached strategy and
                    reroutes capital to next-best eligible
On new high NAV:    Allocator triggers performance fee accrual via x402
On rebalance window: Allocator reassesses target allocation against current ranks
```

---

## 5. User personas and journeys

Helios serves three primary actors. Each has a distinct journey, surface, and economic role.

### 5.1 Persona: The Capital Owner ("Maya")

**Profile.** Crypto-native, holds $5k–$100k in stablecoins, has tried managing her own DeFi positions but finds it time-consuming. Has heard of AI trading agents but wouldn't trust any single one with custody. Knows roughly what "Sharpe ratio" means.

**Goal.** Deploy capital into AI-managed strategies with clear policy guardrails, without giving up custody or having to monitor anything daily.

**Journey.**

1. **Discovery.** Maya finds Helios via the hackathon demo, the live web app, or a Telegram referral.
2. **Onboarding.** Logs in with Kite Passport (passkey + email) — first login provisions her ERC-4337 smart account on Kite via `@gokite-network/auth`. v1 ships and demos on Kite Testnet (chain 2368, network identifier `kite-testnet`); mainnet promotion (chain 2366) is a stretch deliverable, not a planned phase (see roadmap §17). Funds the wallet with 1,000 USDC (testnet faucet at `https://faucet.gokite.ai`; Banxa fiat or `bridge.gokite.ai` cross-chain only if the mainnet stretch is exercised). Reviews three pre-built meta-strategy templates: *Conservative* (max 5% per strategy, max 10% drawdown), *Balanced* (10% / 15%), *Aggressive* (30% / 25%).
3. **Configuration.** Picks Balanced, customizes asset universe to BTC/ETH/SOL only, sets max performance fee at 25%. Reviews the auto-generated meta-strategy in human-readable form. Approves once via passkey — the frontend submits a paymaster-sponsored userOp that batches `USDC.approve` + `UserVault.deposit` + `setMetaStrategy` + `delegateToAllocator` in a single transaction.
4. **Activation.** Within 30 seconds, dashboard shows her capital allocated across 3-5 strategies. Dashboard shows current NAV, allocated capital per strategy, recent trades, current reputation rankings.
5. **Ongoing.** The dashboard activity rail surfaces meaningful events live: strategy added, strategy defunded, weekly P&L summary, fee accrued. She can adjust meta-strategy at any time (next rebalance picks up changes). A Telegram-bot fan-out for the same events is on the post-hackathon Phase 1 roadmap (§17).
6. **Withdrawal.** Hits "Withdraw" — capital pulls from all strategies, performance fees settle, USDC returns to her wallet. End-to-end ~10 minutes.

**Why she stays.** She can see exactly what her capital is doing, every fee is performance-gated, and bad strategies get fired automatically. The transparency is unprecedented for AI-managed capital.

### 5.2 Persona: The Strategy Operator ("Ren")

**Profile.** Quant developer, has built profitable trading strategies but lacks distribution. Either runs a small fund, has been writing strategies as a hobby, or works at a quant shop and wants a side income. Comfortable with Python, knows Solidity at a reading level.

**Goal.** Monetize trading expertise without building a fund, raising capital, or taking custody. Get rewarded purely on realized performance.

**Journey.**

1. **SDK installation.** Ren installs `pip install helios-strategy-sdk`. Reads the docs.
2. **Strategy implementation.** Picks a strategy class (`momentum_v1`). Implements the required `StrategyAgent` interface: `compute_signal()`, `size_trade()`, `should_exit()`. The SDK provides the rest (proof generation, on-chain submission, P&L tracking, reputation reporting).
3. **Local backtesting.** Runs `helios backtest --strategy ./my_momentum.py --period 180d --capital 10000` to validate.
4. **Stake and registration.** Posts $5,000 USDC stake (lower stake = lower visibility in allocator rankings). Registers strategy on the StrategyRegistry with manifest: declared class `momentum_v1`, asset universe `[BTC, ETH, SOL, BNB]`, max capacity $500k, fee rate 20%.
5. **Deployment.** Runs `helios deploy --strategy ./my_momentum.py --vps user@his-server`. Docker image deploys, agent starts trading whenever it receives allocations.
6. **Earning.** Allocators discover his strategy via the registry, allocate capital based on reputation. Ren earns 20% of realized profit above HWM per allocation. Fees stream via x402 and accumulate in his strategy operator wallet.
7. **Reputation building.** Initial reputation is low (no track record). After 30 days of consistent execution and proof validity, his reputation rises. Allocators progressively allocate more capital. After 90 days he's a top-10 momentum strategy and capacity becomes the binding constraint.

**Why he stays.** Pure performance economy, no fundraising. He competes on actual returns, not on marketing. His track record is portable, on-chain, and ZK-attested.

### 5.3 Persona: The Allocator Operator ("Sara")

**Profile.** Quant fund operator, DAO treasury manager, or sophisticated individual who wants to provide allocation services to many users with their own custom ranking algorithm. Comfortable with Python, understands portfolio theory and risk management.

**Goal.** Provide allocation services to many users, earn meta-fees on aggregate performance, build a track record that attracts more delegated capital over time.

**Journey.**

1. **SDK installation.** Sara installs `pip install helios-allocator-sdk`. Reads the docs.
2. **Allocator implementation.** Picks the `BaseAllocator` interface and implements her custom ranking function (e.g., volatility-adjusted Sharpe with cohort-relative scoring + correlation-aware allocation). The SDK provides the rest (capital deployment, drawdown monitoring, fee crystallization, defund triggers).
3. **Local backtesting.** Runs `helios-allocator backtest --allocator ./my_allocator.py --strategies <ids> --capital 50000 --period 180d` to validate.
4. **Stake and registration.** Posts $10,000 USDC stake (allocator stake is required because users trust allocators with their capital — slashable on policy violations). Registers on the AllocatorRegistry with manifest: ranking function hash, allocator fee rate, supported strategy classes, max users.
5. **Deployment.** Runs `helios-allocator deploy --vps user@her-server`. Docker image deploys, allocator runs continuously.
6. **User onboarding.** Users discover Sara's allocator via the web app's allocator marketplace. They review her ranking function, fee rate, performance history, and stake before delegating to her.
7. **Earning.** Sara earns 5% of net realized profit above HWM across all delegated capital. Fees stream via x402.
8. **Reputation building.** Sara's allocator earns its own reputation score, tracked separately from strategy reputations. Allocators with better aggregate user outcomes attract more delegations.

**Why she stays.** Pure performance economy at the allocator layer. She competes with other allocators on the quality of her ranking function and risk management — not on marketing or sales. Her track record is portable and ZK-attested at the underlying strategy level.

### 5.3.1 Helios Sentinel — the reference allocator

For the MVP demo, the Helios team operates **Helios Sentinel**, the reference allocator implementation. Sentinel is a fully-functional allocator that ships as the first concrete allocator on the network — it's not a stub, it's the canonical implementation that other allocator operators will fork and modify.

**Sentinel is a brand.** The name "Helios Sentinel" is reserved for the team's reference allocator. Third parties shipping allocators via the AllocatorSDK must register under different names. This is intentional — Sentinel sets the quality bar for what an allocator should be, and the brand carries trust during the bootstrap phase. Post-hackathon, allocator competition emerges; users will be able to choose between Sentinel and competing allocators in the marketplace.

**Sentinel's ranking function** is the reference implementation described in Section 11.2. It's deliberately legible and conservative: a clean reputation-weighted top-K with capacity factor and fee-fit gating. Allocators that ship more sophisticated algorithms (correlation-aware allocation, regime-adaptive weights, ML-based strategy fit) can demonstrate clear improvements over Sentinel and attract users on that basis.

**For the MVP demo, Sentinel and at least one third-party reference allocator both exist** — the second one is intentionally shipped as a "competing allocator" to demonstrate the marketplace mechanism even within the hackathon.

### 5.4 Cross-cutting: the Auditor

Anyone — judges, journalists, prospective users, regulators — can act as an auditor. Without permission, they can:

- Browse the public Strategy Registry and see every strategy's manifest, current reputation, stake, fee rate, and historical P&L.
- Verify any individual trade's ZK proof was valid (re-run the verifier off-chain).
- Reconstruct any user's allocation history from on-chain events.
- Verify performance fees were charged correctly against high-water marks.
- Replay the full trade history of any strategy to validate reputation scores.

This is intentional — auditability is a primary product feature, not a compliance afterthought. Inherited from the KiteClaw approach to auditable agent runs.

---

## 6. On-chain components — smart contracts

Helios's on-chain surface is intentionally minimal. The novelty is in the autonomous loop, not in a sprawling contract system. Seven primary contracts on Kite, plus mirrored verifiers and OApp endpoints on Base and Arbitrum.

### 6.1 Contract inventory

| Contract | Chain(s) | Purpose | Approx LoC |
|---|---|---|---|
| `UserVault` | Kite | Per-user capital custody, meta-strategy enforcement, allocator sub-delegation | ~400 |
| `AllocatorVault` | Kite | Per-allocator capital custody, strategy sub-delegation, performance fee escrow | ~350 |
| `StrategyVault` | Kite, Base, Arbitrum | Per-strategy capital custody, ZK-gated trade execution, NAV tracking | ~500 |
| `StrategyRegistry` | Kite | Strategy manifests, stake, reputation anchor | ~300 |
| `AllocatorRegistry` | Kite | Allocator manifests, allocator stake, allocator reputation anchor, reserved-name registry (protects the Sentinel brand) | ~250 |
| `TradeAttestationVerifier` | Kite, Base, Arbitrum | Verifies Groth16 proofs for trade attestations; per strategy class | ~150 (+ generated verifier) |
| `ReputationAnchor` | Kite | Receives reputation deltas from off-chain engine and from cross-chain LayerZero messages; canonical source of both strategy and allocator scores | ~280 |
| `OraclePriceAnchor` | Kite, Base, Arbitrum | Receives EIP-712 signed price snapshots from the Helios oracle; publishes the canonical Poseidon `oracle_root` consumed by ZK proofs and the TWAP feed used by the auto-defund drawdown trigger (§6.3, §6.4) | ~220 |
| `OracleYieldAnchor` | Arbitrum | Receives EIP-712 signed APY snapshots; publishes the Poseidon `yield_oracle_root` consumed by `yield_rotation_v1` proofs (§9.4) | ~180 |
| `HeliosOApp` | Kite, Base, Arbitrum | LayerZero OApp for cross-chain reputation messages and capital bridging hooks | ~200 |

Total Solidity surface area: roughly 2,830 LoC, plus generated Groth16 verifiers (one per strategy class). Tight enough to be auditable in a hackathon timeframe.

### 6.2 `UserVault`

The user's capital home. UUPS-upgradeable, owned by the user's Passport-issued ERC-4337 smart account; meta-strategy writes are gated by `msg.sender == owner` (the AA wallet), so the user's passkey approval at the Passport layer flows through to on-chain authorization without a separate EIP-712 signature path.

**State.**

```solidity
struct MetaStrategy {
    bytes32 metaStrategyHash;       // Poseidon hash of the meta-strategy fields below; emitted in MetaStrategySet
    address[] allowedStrategyClasses;
    address[] allowedAssets;
    address[] allowedChains;
    uint256 maxCapital;
    uint256 maxPerStrategyBps;      // e.g., 3000 = 30%
    uint256 maxStrategiesCount;
    uint256 drawdownThresholdBps;   // e.g., 1500 = 15%
    uint256 maxFeeRateBps;          // e.g., 2500 = 25%
    uint256 rebalanceCadenceSec;
    uint64  validUntil;
    uint16  defundTwapBars;         // §6.3 anti-grief bars — schema landed in build phase 2; enforcement in build phase 4 (see TODO.md; distinct from §17 post-hackathon roadmap phases)
    uint16  defundBondBps;          // §6.3 anti-grief bond
    uint32  defundConfirmBlocks;    // §6.3 anti-grief confirmation window
    uint16  defundRewardCapUsd;     // §6.3 reward cap on permissionless trigger (default 500 USDC, 6 decimals)
    uint16  bootstrapShareBps;      // §8.7 cold-start pool (Sentinel honors)
    uint32  minAttestedTrades;      // §8.7 cold-start eligibility threshold
}

mapping(address => MetaStrategy) public userMetaStrategies;
mapping(address => address) public userAllocator;     // user -> assigned allocator
mapping(address => uint256) public userHighWaterMark; // for allocator fee accrual
```

**Key functions.**

```solidity
function setMetaStrategy(MetaStrategy calldata meta) external;
function deposit(uint256 amount) external;                     // typically batched with USDC.approve in one userOp
function delegateToAllocator(address allocator) external;       // on-chain ACL; revoke = call again with address(0)
function withdraw(uint256 amount) external;
function settleAllocatorFee() external;
```

**Trust constraints.**

- Only the AA wallet (the user, via their Passport login) can `setMetaStrategy`, `delegateToAllocator`, or `withdraw`. Authorization is `msg.sender == owner` enforced by the AA wallet's userOp signature check at the EntryPoint.
- The allocator can pull capital up to the user's allocated portion, but cannot exceed the meta-strategy's `maxCapital`. Out-of-bounds allocations revert in `AllocatorVault`.
- Allocator delegation has no on-chain TTL in v1 — revocation is `delegateToAllocator(address(0))`. A session TTL field could be added in v2 if Passport ships expiring delegations natively.
- `settleAllocatorFee` computes fee = `max(0, currentNAV - userHighWaterMark) * allocatorFeeRate`. Updates HWM atomically.

### 6.3 `AllocatorVault`

The allocator's working capital, holding pending deployments and accrued fees.

**State.**

```solidity
struct AllocationRecord {
    address strategy;
    uint256 capitalDeployed;
    uint256 strategyHWM;            // HWM for this specific allocation
    uint256 lastRebalanceTimestamp;
    uint64  defundedAt;             // 0 if active
}

mapping(address => mapping(address => AllocationRecord)) public allocations; // user -> strategy -> record
mapping(address => uint256) public accruedFees;
```

**Key functions.**

```solidity
function allocateToStrategy(address user, address strategy, uint256 amount) external;
function defundStrategy(address user, address strategy, string calldata reason) external;
function rebalance(address user, address[] calldata strategies, uint256[] calldata weightsBps) external;
function settleStrategyFee(address user, address strategy) external;
function withdrawAllocatorFees() external;
```

**Trust constraints.**

- Only the allocator EOA (or its session keys) can call `allocateToStrategy`, `defundStrategy`, `rebalance`.
- All allocation amounts are checked against the user's meta-strategy.
- `defundStrategy` is callable by anyone (permissionless trigger), but only when the drawdown breach is **persistent** — held across at least `defundTwapBars` consecutive observations spaced ≥ `MIN_BAR_BLOCKS` apart (default 3 bars × 300 blocks ≈ 15 minutes on Kite's 1s blocks) — and the caller posts a forfeit bond. The permissionless path is split into `triggerDefund` (each call is one observation; the first call posts the bond, subsequent calls advance the breach counter; a non-breaching observation clears the entry and refunds the bond) and `finalizeDefund` (callable once the entry is armed and `defundConfirmBlocks` have elapsed since the last observation). The bond is refunded plus a reward of **50 bps of the defunded notional, capped at $500 USDC** if the breach is confirmed at finalize; slashed to the user's vault if NAV recovers above threshold by the time finalize runs. **Reward source — v1 deviation:** the original §6.3 design routed the reward from the strategy's stake (so the user is held harmless and the bad operator pays). In v1 the reward is instead routed from `AllocatorVault._accruedFees` — the allocator's own pool of unharvested fees — because `StrategyRegistry` is immutable in Phase 3 and adding a `payDefundReward` path would require a full registry redeploy + re-registration of every existing strategy. The economics still work: the allocator's incentive to keep their accruedFees pool high is to avoid going offline (an offline allocator gets defund-watchdog'd, losing fees to the watchdog) — pressure flows in the right direction. The user remains held harmless either way (their principal isn't touched). v2 migrates to the original "from stake" routing once the registry is rebuilt (see §17 Phase 1). If the allocator's accruedFees are insufficient, the reward is paid down to whatever is available (bond is always refunded in full). This preserves the safety property (anyone can fire if the allocator goes offline) while closing a griefing surface where a competitor times a transient mark-to-market dip to lock in losses that would have mean-reverted. The persistence depth, bond size, confirmation window, and reward cap are configurable per-user in the meta-strategy (`defundTwapBars`, `defundBondBps`, `defundConfirmBlocks`, `defundRewardCapUsd`); `MIN_BAR_BLOCKS` and `MAX_STALENESS_SEC` are owner-tuned vault constants.
- **Drawdown source.** Drawdown is sampled from `IStrategyVault.navOf(address(this))` on each observation and compared against the allocation's `strategyHighWaterMark`. Phase 2 oracle ships Poseidon-root commitments only, not per-asset on-chain TWAP prices, so a fully on-chain-priced "marked NAV" path is not available in v1 — the Phase 4 implementation relies on the operator's `reportNAV`-driven `navOf()` for the observation signal and on the §6.4 NAV-divergence slash path (`NAV_DIVERGENCE_THRESHOLD_BPS`, two-consecutive trigger) as the deterrent against a malicious operator signing a flattering NAV to suppress defund. The oracle is still consulted: `OraclePriceAnchor.latest().committedAt` gates the *first* observation as a coarse "the oracle hasn't gone offline" signal — if `block.timestamp - committedAt > MAX_STALENESS_SEC` the trigger reverts. A genuine TWAP-priced "marked NAV" computed on-chain (Algebra V3 pool TWAPs on Kite mainnet, or a per-asset price-anchor service) is roadmap (§17 Phase 1).
- `reason` is logged on-chain (e.g., `"DRAWDOWN_BREACH"`, `"RANK_DROP"`, `"USER_REBALANCE"`).

### 6.4 `StrategyVault`

The per-strategy capital home. Trades flow through here. ZK-gated execution.

**State.**

```solidity
struct StrategyManifest {
    bytes32 declaredClass;          // ClassIds.MOMENTUM_V1 etc. — Poseidon-derived; BN254-fit
    address[] assetUniverse;
    uint256 maxCapacity;
    uint16  feeRateBps;
    address operator;
    uint256 stakeAmount;
}

StrategyManifest public manifest;
mapping(address => uint256) public allocations;  // allocator -> capital deployed
mapping(address => uint256) public navPerAllocator;
uint256 public totalNAV;
uint256 public lastSettlementBlock;
address public attestationVerifier;
```

**Key functions.**

```solidity
function executeWithProof(
    bytes calldata proof,
    bytes calldata publicInputs,
    Call[] calldata trades
) external onlyOperator;

function reportNAV(bytes calldata signedNAV) external;
function distributeRealized(address allocator) external;
function withdrawToAllocator(address allocator, uint256 amount) external;
function slash(string calldata reason) external onlyRegistry;
```

**Trust constraints.**

- `executeWithProof` requires a valid Groth16 proof binding the trade calldata to the strategy's declared class. The verifier contract is set at deploy time and cannot be changed (immutable on the manifest). If the proof is invalid, execution reverts and the trade does not happen.
- `reportNAV` is signed by the **strategy operator** and is used both for performance attribution (off-chain Sharpe, P&L curves, fee crystallization triggers) and — in Phase 4's caller-cadence defund path (§6.3) — as the on-chain NAV signal the permissionless trigger samples. The Phase 2 oracle architecture commits Poseidon roots only, not per-asset on-chain TWAP prices, so a fully oracle-priced "marked NAV" comparison is not available in v1. Operator-signed NAV is therefore in the trust path for defund observation. The Phase 4 deterrent is a **one-sided NAV-divergence slash path**: long-only spot classes (momentum / mean-reversion / yield-rotation) satisfy the invariant `NAV ≥ cashHeld`, so a signed NAV that falls below the strategy vault's `baseAsset.balanceOf(this)` cash floor by more than **`NAV_DIVERGENCE_THRESHOLD_BPS = 500` (5%)** for two consecutive snapshots emits `NavDivergenceObserved(strategy, signed, marked, snapshotNonce)`. The Helios multi-sig watches the event off-chain and executes `StrategyRegistry.slash(strategy, amount, "NAV_DIVERGENCE")` (no on-chain queue — `StrategyRegistry` is immutable in Phase 3 and adding `queueSlash` would require a full redeploy + re-registration; deferred to v2 alongside the §17 registry rebuild). The cash-floor check catches **operator under-reporting** (an attack vector against drawdown calculations and fee suppression). The complementary attack — **operator over-reporting** to hide a real drawdown and suppress defund — requires an upper-bound NAV recomputation, i.e., a per-asset on-chain price source for the non-cash legs of the strategy's asset universe. That source doesn't exist on Kite testnet/mainnet in v1 (no Pyth/Chainlink, no Algebra-pool-TWAP read), so over-reporting detection is deferred to v2 / post-hackathon (`§17` Phase 1) when the per-asset TWAP anchor ships. The 5% threshold is calibrated to be wider than typical legitimate sources of divergence (intra-bar price moves, in-flight swaps) but tight enough that sustained dishonesty is unambiguous; the parameter is owner-controlled in v1 (Helios multi-sig) with a clear v2 path to per-class governance — see §15.1 for the centralization callout.
- `slash` can only be called by `StrategyRegistry` (e.g., on detected misbehavior — invalid NAV reports, repeated proof failures, manifest-divergent trades).
- All capital flows are tracked per-allocator so multiple allocators can co-invest in the same strategy.

### 6.5 `StrategyRegistry`

The canonical strategy directory on Kite.

**State.**

```solidity
struct StrategyEntry {
    address vault;                  // StrategyVault address
    address operator;
    bytes32 declaredClass;
    uint256 stakeAmount;
    uint256 currentReputation;      // updated by ReputationAnchor
    uint64  registeredAt;
    bool    active;
}

mapping(address => StrategyEntry) public strategies;
address[] public strategyList;
mapping(bytes32 => address[]) public strategiesByClass;
```

**Key functions.**

```solidity
function registerStrategy(
    address vault,
    bytes32 declaredClass,
    uint256 stakeAmount
) external returns (address strategyId);

function topUpStake(address strategyId, uint256 amount) external;
function withdrawStake(address strategyId, uint256 amount) external;
function deactivate(address strategyId) external;
function updateReputation(address strategyId, int256 delta) external onlyReputationAnchor;
function slash(address strategyId, uint256 amount, string calldata reason) external onlyOwner;
function rotateParams(address strategyId, bytes32 newParamsHash) external onlyOperator;
function setMarketAllowlistRoot(bytes32 declaredClass, bytes32 root) external onlyOwner;
```

**Trust constraints.**

- `registerStrategy` requires posting `stakeAmount` in USDC. Permissionless. The manifest's `paramsHash` is committed at registration and bound into every ZK proof's public inputs (§9.3).
- `rotateParams` lets the operator change `manifest.paramsHash` only after a public, observable cooldown (default 24h after the last rotation, enforced by the registry). Rotation emits a `ParamsRotated` event and creates a clean break in the strategy's track record: the reputation engine resets `AgeScore` and `PerformanceScore` on the new params slot, and allocators see the rotation timestamp so they can choose whether to keep or pull capital. This forecloses the "pick a threshold to fit each trade" attack because the threshold is fixed across all trades under a given `paramsHash` and any change is publicly visible before the next trade.
- `slash` is owner-controlled in the MVP (Helios team multi-sig), with a clear path to community governance post-hackathon.
- `withdrawStake` has a 7-day cooldown to prevent rug-pulls after taking allocations.
- `setMarketAllowlistRoot` lets the registry publish a Merkle root over the markets allowed for a class (used by `yield_rotation_v1` per §9.4). Owner-only in v1 (Helios multi-sig curates the lending venues for `yield_rotation_v1`); see §15.1 for the centralization implications and the v2 path to per-class governance.

### 6.6 `AllocatorRegistry`

The canonical allocator directory on Kite. Mirrors `StrategyRegistry` in shape but tracks allocators (Helios Sentinel, Helios Helix, and any third-party allocators built on the AllocatorSDK) rather than strategies. It also enforces the reserved-name policy that protects the Sentinel brand.

**State.**

```solidity
struct AllocatorEntry {
    string  name;                   // e.g., "Helios Sentinel", "Helios Helix", "VolatilityAware"
    address operatorVault;          // AllocatorVault address for this allocator
    address operator;
    bytes32 rankingFunctionHash;    // Poseidon hash of the allocator's ranking function code
    bytes32[] supportedClasses;     // strategy classes this allocator will allocate to
    uint16  feeRateBps;             // e.g., 500 = 5%
    uint256 stakeAmount;            // allocator's stake at risk
    int256  currentReputation;      // updated by ReputationAnchor (actor_type = ALLOCATOR)
    uint256 totalUsers;
    uint256 totalCapitalManaged;
    uint64  registeredAt;
    bool    active;
    bool    isReferenceBrand;       // true for Sentinel and Helix; locks the name
}

mapping(address => AllocatorEntry) public allocators;
address[] public allocatorList;
mapping(bytes32 => bool) public reservedNames;  // Poseidon("helios sentinel"), etc.
mapping(bytes32 => address) public nameToAllocator;
```

**Key functions.**

```solidity
function registerAllocator(
    string calldata name,
    address operatorVault,
    bytes32 rankingFunctionHash,
    bytes32[] calldata supportedClasses,
    uint16 feeRateBps,
    uint256 stakeAmount
) external returns (address allocatorId);

function topUpStake(address allocatorId, uint256 amount) external;
function withdrawStake(address allocatorId, uint256 amount) external;
function deactivate(address allocatorId) external;
function updateReputation(address allocatorId, int256 delta) external onlyReputationAnchor;
function slash(address allocatorId, uint256 amount, string calldata reason) external onlyOwner;

// Reserved-name administration (Helios team multi-sig only)
function reserveName(string calldata name) external onlyOwner;
function assignReferenceBrand(address allocatorId) external onlyOwner;
```

**Trust constraints.**

- `registerAllocator` requires posting `stakeAmount` in USDC. Permissionless for any name not on the reserved list.
- Attempting to register with a reserved name (`"Helios Sentinel"`, `"Helios Helix"`, `"Helios *"` variants, etc.) reverts. The reserved-name list is expandable by the Helios team multi-sig during the MVP; post-hackathon governance can adjust policy.
- Only addresses pre-approved by the Helios multi-sig can have `isReferenceBrand = true`. This distinction surfaces as an "Official Reference" badge in the web app's `/allocators` directory.
- `withdrawStake` has the same 7-day cooldown as `StrategyRegistry`, to prevent allocator rug-pulls after taking user delegations.
- Allocator reputation is computed off-chain (see Section 11.5) and anchored here via `ReputationAnchor.postReputationUpdate` with `actor_type = ALLOCATOR`.

**Why this contract is necessary.** Without `AllocatorRegistry`, "the marketplace" exists only as a narrative claim — users couldn't discover allocators, allocators couldn't build on-chain reputation, and the Sentinel brand would have no on-chain enforcement. With it, the two-sided market (strategies compete for allocator capital, allocators compete for user capital) becomes a real on-chain structure, not a frontend abstraction.

### 6.7 `TradeAttestationVerifier`

A thin wrapper around the snarkjs-generated Groth16 verifier for each strategy class. Per strategy class, per chain.

**State.**

```solidity
mapping(bytes32 => address) public verifiersByClass; // declared class -> Groth16 verifier
```

**Key function.**

```solidity
function verify(
    bytes32 declaredClass,
    bytes calldata proof,
    uint256[] calldata publicInputs
) external view returns (bool);
```

Public inputs include: trade hash (Poseidon of the calldata), strategy declared class, asset addresses involved, trade direction (long/short flag), trade size, slippage bound, time window, allocator address. All of these get checked inside the circuit (see Section 9).

### 6.8 `ReputationAnchor`

Receives reputation updates from the off-chain Reputation Engine and from cross-chain LayerZero messages. Anchors reputation for **both strategies and allocators**, distinguished by an `actor_type` flag. This is what makes Helios a two-sided reputation market.

**State.**

```solidity
enum ActorType { STRATEGY, ALLOCATOR }

struct ReputationData {
    int256  currentScore;           // range: e.g., -10000 to +10000
    uint256 lastUpdateBlock;
    uint256 totalAttestedTrades;    // for strategies; for allocators: total rebalance ops
    uint256 totalRealizedPnL;       // for strategies: own P&L; for allocators: aggregate user P&L
    uint256 maxDrawdownBps;
    uint256 proofValidityRateBps;   // for strategies; always 10000 for allocators
    ActorType actorType;
}

mapping(address => ReputationData) public reputations;
mapping(address => uint64) public lastUpdateBySource; // source -> timestamp
```

**Key functions.**

```solidity
function postReputationUpdate(
    address actor,
    ActorType actorType,
    ReputationData calldata data,
    bytes calldata signerSignature
) external;

function postCrossChainUpdate(
    address actor,
    ActorType actorType,
    ReputationData calldata data
) external onlyOApp;
```

**Trust constraints.**

- Off-chain engine updates require a signature from the Helios reputation signer (a registered EOA with a known address). This is a centralization point in the MVP that is documented and addressed in the post-hackathon roadmap (move to a quorum of signers, then to ZK-attested computation).
- Cross-chain updates can only come from the registered LayerZero OApp endpoint.
- All updates emit events for Goldsky indexing.
- Downstream: `StrategyRegistry.updateReputation` and `AllocatorRegistry.updateReputation` both read from this anchor via `onlyReputationAnchor`-gated setters.

### 6.9 `HeliosOApp`

The LayerZero OApp endpoint for cross-chain coordination. Deployed on Kite, Base, and Arbitrum.

**Functions.**

```solidity
function sendReputationUpdate(
    uint32 dstEid,
    address strategy,
    ReputationData calldata data,
    bytes calldata options
) external payable;

function _lzReceive(
    Origin calldata origin,
    bytes32 guid,
    bytes calldata payload,
    address executor,
    bytes calldata extraData
) internal override;

function quote(
    uint32 dstEid,
    bytes calldata payload,
    bytes calldata options
) external view returns (MessagingFee memory);
```

Strategy vaults on Base/Arbitrum push their NAV updates and trade attestations through HeliosOApp to the Kite-side ReputationAnchor.

### 6.10 `OraclePriceAnchor` and `OracleYieldAnchor`

The two oracle-anchor contracts publish the canonical commitments that the rest of the system reads from. Both are immutable (no UUPS proxy), permissioned to a single registered Helios oracle signer (rotation requires owner-multi-sig), and emit one event per snapshot so Goldsky and the dashboard can stream them.

**`OraclePriceAnchor`** is load-bearing in two places in v1: (a) every Groth16 proof's `oracle_root` public input must equal a root anchored here within a freshness window enforced by `StrategyVault.executeWithProof` (and validated against the per-root `freshness(root)` view), and (b) the auto-defund permissionless trigger (§6.3) reads `latest().committedAt` as a coarse "the oracle hasn't gone offline" gate. A compromised price oracle falsifies proof validation and corrupts the freshness gate — see §15.2. *Note:* the v1 anchor commits Poseidon roots only — per-asset on-chain price reads are not exposed. The auto-defund path therefore samples NAV from `IStrategyVault.navOf()` (§6.3) rather than recomputing from on-chain prices; a fully on-chain-priced TWAP path is roadmap.

```solidity
struct Commit {
    bytes32 root;               // Poseidon root over the per-asset price snapshot ring
    uint64  windowStart;        // earliest snapshot ts_ms (inclusive)
    uint64  windowEnd;          // latest snapshot ts_ms (inclusive)
    uint64  committedAt;        // block.timestamp at write
    address signer;             // recovered EIP-712 signer (audit only)
}

Commit[] internal _commits;

function commit(bytes32 root, uint64 windowStart, uint64 windowEnd, bytes calldata sig) external;
function latest() external view returns (Commit memory);
function commitCount() external view returns (uint256);
function commitAt(uint256 index) external view returns (Commit memory);
function isKnownRoot(bytes32 root) external view returns (bool);
function freshness(bytes32 root) external view returns (uint64 committedAt);  // 0 if unknown/revoked
function revokeRoot(bytes32 root) external;     // owner-gated
function unrevokeRoot(bytes32 root) external;   // owner-gated; reverses a misclick revoke
```

**`OracleYieldAnchor`** mirrors the shape but commits per-market APYs as a Poseidon-Merkle root over up to 64 lending markets (depth 6). Read by `yield_rotation_v1` proofs (§9.4); not used by the auto-defund path.

**Trust constraints.**

- Only the registered oracle EOA can sign `commit`. Rotation goes through the Helios multi-sig (same model as the reputation signer in §15.1).
- `freshness(root)` is the per-root staleness query that `StrategyVault.executeWithProof` uses — proofs whose `oracle_root` is older than `MAX_STALENESS_SEC` (default 180s) revert. The defund permissionless trigger separately reads `block.timestamp - latest().committedAt` against the same window and reverts with `OracleStale` on its first observation if the oracle has gone quiet.
- `revokeRoot` / `unrevokeRoot` let the owner kill (and resurrect) a single committed root without touching the signer key — the recovery path for an oracle compromise where the offending roots are known.
- `OracleYieldAnchor` commits are posted on a 5-minute cadence; yield-rotation proofs include the snapshot nonce in their public inputs and the contract validates monotonicity via `windowStart >= prev.windowEnd`.
- Both anchors are listed as v1 trust assumptions in §15.1 and as threat-model entries in §15.2. Post-hackathon roadmap (§17) replaces the Helios-operated oracles with Pyth/Chainlink adapters and adds a per-asset on-chain TWAP anchor for defund marked-NAV.

---

## 7. Off-chain components — services

Helios runs four off-chain services. All are stateless (with state persisted to Postgres + on-chain) and Dockerized for portability.

### 7.1 Service inventory

| Service | Language | Purpose | Hosted by |
|---|---|---|---|
| **Helios Sentinel** | Python (FastAPI) | The reference allocator agent — ranks strategies, makes allocation decisions, monitors drawdowns, triggers rebalances and defunds. Branded reference; competing allocators ship via the AllocatorSDK. | Helios team (verified set); SDK lets third parties self-host competing allocators |
| **Strategy Service** | Python (FastAPI) | Reference strategy agents (momentum, mean-reversion, yield-rotation) — execute trades, generate ZK proofs | Helios team for demo; SDK lets others self-host |
| **Reputation Engine** | Python (FastAPI) | Consumes Goldsky subgraph data; computes reputation scores; signs and posts updates to ReputationAnchor | Helios team |
| **Prover Service** | Node.js (snarkjs over HTTP) | Generates Groth16 proofs from trade specs and witness inputs | Co-located with each strategy agent |

### 7.2 Service interaction map

```
   ┌─────────────────────┐          ┌────────────────────────┐
   │  Allocator Service  │◀────────▶│  Goldsky Subgraph API  │
   │     (Python)        │          │  (read-only)           │
   └────┬────────────────┘          └────────────────────────┘
        │ delegate / defund / rebalance
        │ submitted as userOps from the
        │ allocator's registered EOA
        ▼
   ┌─────────────────────┐
   │  Kite RPC + Bundler │
   │  (gokite-aa-sdk)    │
   └────┬────────────────┘
        │
        ▼
   ┌─────────────────────┐          ┌──────────────────────┐
   │  Strategy Service   │─────────▶│  Prover Service      │
   │     (Python)        │   POST   │  (Node + snarkjs)    │
   │  per strategy       │          │  generates Groth16   │
   └────┬────────────────┘          └──────────────────────┘
        │ executeWithProof
        ▼
   ┌─────────────────────┐
   │ Chain RPC (Kite/    │──────────emits TradeAttested──────┐
   │ Base/Arbitrum)      │                                   ▼
   └─────────────────────┘                          ┌──────────────────┐
                                                    │ Goldsky Indexer  │
                                                    └──────┬───────────┘
                                                           │
                                                           ▼
                                                ┌──────────────────────┐
                                                │ Reputation Engine    │
                                                │ (Python)             │
                                                │ Computes scores      │
                                                │ Posts updates        │
                                                └──────────┬───────────┘
                                                           │
                                                           ▼
                                                  ReputationAnchor
                                                     (Kite L1)
```

### 7.3 Helios Sentinel — the reference allocator service

A Python FastAPI service implementing the reference allocator. Stateless (state persists in Postgres + on-chain). For the MVP, runs as a single process on the Helios VPS with PM2 supervision. Branded as **Helios Sentinel**; competing allocators ship via the AllocatorSDK (Section 11.3) and run their own services with their own branding.

**Core responsibilities.**

1. **User onboarding.** Read the user's `MetaStrategy` from `UserVault` (set by the user's AA wallet via the frontend). Persist hash and constraints. Confirm the user has called `delegateToAllocator(this)` so on-chain ACL grants this allocator authority.
2. **Strategy discovery.** Periodically (every 60s) query Goldsky subgraph for active strategies matching the meta-strategy's allowed classes and assets. Filter by minimum stake, minimum reputation, available capacity.
3. **Ranking and allocation.** Apply the ranking function (Section 8) to eligible strategies. Compute target allocation given the user's `maxPerStrategyBps`, `maxStrategiesCount`, and current capital. Diff against current allocation. Issue delta operations.
4. **Drawdown monitoring.** Every 5 minutes, poll each StrategyVault's NAV. Compute drawdown from per-allocation HWM. If breached, emit defund tx immediately.
5. **Rebalancing.** On meta-strategy's `rebalanceCadenceSec` cycle, recompute target allocation and emit migration ops.
6. **Fee settlement.** When NAV exceeds HWM by a configurable threshold (e.g., 1%), trigger `settleStrategyFee` to crystallize allocator fees.

**Key endpoints.**

```
POST /v1/users/{user}/meta-strategy        — register the user (allocator reads on-chain MetaStrategy after this call)
GET  /v1/users/{user}/dashboard            — current allocation + NAVs + fees + history
GET  /v1/users/{user}/timeline             — chronological event log
POST /v1/users/{user}/withdraw             — initiate full unwinding
GET  /v1/strategies                         — public strategy directory
GET  /v1/strategies/{id}                    — strategy detail
WS   /v1/users/{user}/events               — server-sent events for the dashboard
```

### 7.4 The Strategy Service

A Python FastAPI service that wraps a strategy class. The Helios team ships reference implementations:

- **`momentum_v1`** — long when 10-period return on a bar exceeds threshold, exit on opposite signal or stop-loss.
- **`mean_reversion_v1`** — short on N-sigma upward deviation, long on N-sigma downward, exit on mean re-cross.
- **`yield_rotation_v1`** — periodically scans allowlisted lending markets across chains; moves capital from lower-APY markets to higher-APY markets when the rate differential exceeds a threshold (net of bridging cost). Strategy-internal accounting tracks the realized yield earned per allocation.

**Core responsibilities.**

1. **Receive allocations.** Listen for AllocationCreated events on the StrategyVault. Update internal capital tracker.
2. **Market data ingestion.** Poll OKX/Binance/Coinbase price feeds (websocket where available). For the MVP, use direct API access; document the path to migrating to x402-paid feeds in v2.
3. **Signal computation.** On each bar close (1-minute resolution for the MVP), compute the strategy's signal.
4. **Trade construction.** When a signal triggers, construct the trade: target asset, direction, size (per `size_trade()`), max slippage, time window.
5. **Proof generation.** Submit trade spec + market state to the Prover Service. Receive Groth16 proof.
6. **Execution.** Call `StrategyVault.executeWithProof()` with the proof and trade calldata. The on-chain verifier confirms the proof; the trade executes (e.g., via Algebra DEX router on Kite, Uniswap V3 on Base, etc.).
7. **NAV reporting.** Every 5 minutes (or on-demand), compute current NAV (cash + position market value) and post to the StrategyVault.
8. **Fee handling.** On `distributeRealized` calls, claim accrued fees to the operator's wallet.

### 7.5 The Reputation Engine

The economic brain. Reads attested trade data from Goldsky, computes scores, signs and posts updates.

Detailed in Section 8.

### 7.6 The Prover Service

A Node.js HTTP service wrapping snarkjs. Receives a `{ strategyClass, witnessInputs, publicInputs }` payload, returns `{ proof, publicSignals }`.

**Why a separate service.** snarkjs is heavy; isolating it lets us scale provers independently. Co-located with each strategy agent for low latency.

**Performance budget.** For the strategy classes we ship, target proof generation under 2 seconds on commodity VPS hardware. This is achievable for the circuit complexity we're targeting (~10k–30k constraints; see Section 9).

**Fallback.** If the prover service is unreachable for >30 seconds, the strategy agent enters degraded mode: it pauses new trades and emits an alert. Trades cannot execute without proof — this is by design. There's no `executeDirectly` escape hatch in StrategyVault. (This is a key difference from VAEB, which had a fallback path. We intentionally don't, because the whole reputation system depends on every counted trade having a valid proof.)

---

## 8. The reputation engine

Reputation is the heart of Helios. It's the signal that drives capital allocation, it's the IP that's hard to copy, and it's the thing that has to be both economically defensible and demonstrable in a hackathon demo.

### 8.1 Design principles

1. **Computed from realized, attested behavior only.** A strategy's reputation comes from trades that hit the chain *with valid ZK proofs*. Marketing, social signals, and unverified claims contribute nothing.
2. **Stake-weighted, with a logarithmic cap.** Higher operator stake → higher reputation impact, blunted by the log curve in `StakeScore` (see §8.2: a 100× capital advantage yields ~3.4× score boost, not 100×). A strategy with $50k stake and a 1.5 Sharpe ranks above a strategy with $5k stake and a 1.6 Sharpe, all else equal. This is a **deliberate tradeoff**, not a free win: it makes Sybil farming expensive (the dominant attack on permissionless reputation) at the cost of giving capital-rich operators a bounded structural advantage over equally-skilled small operators. The log curve blunts whale dominance but does not eliminate it. v2 considers a separate stake-stripped sub-rank so users can choose between the capital-weighted and pure-skill signals (§8.5).
3. **Lookback-disciplined.** Score uses rolling windows (7d, 30d, 90d) with explicit weights. New strategies have low scores until they accumulate history.
4. **Drawdown-penalized.** Strategies that achieve returns through high drawdowns rank below strategies with smoother performance, even at equal Sharpe.
5. **Proof validity tracked.** Strategies with proof failures (an invalid proof attempt counts against them) get reputation penalties even if they self-correct.
6. **Cohort-relative.** A strategy is scored relative to other strategies of the same declared class. A momentum strategy is judged against other momentum strategies, not against mean-reversion strategies. This avoids penalizing whole asset classes during regime shifts.
7. **Deterministic given inputs.** The score is a pure function of indexed events. Anyone can re-run the engine on the same data and get the same answer. No secret weights, no proprietary tweaks.

### 8.2 The score formula (v1)

For a strategy `s` of class `c`, at time `t`:

```
ReputationScore(s, t) = w_perf * PerformanceScore(s, t)
                      + w_risk * RiskScore(s, t)
                      + w_proof * ProofScore(s, t)
                      + w_stake * StakeScore(s, t)
                      + w_age * AgeScore(s, t)

where w_perf + w_risk + w_proof + w_stake + w_age = 1.0
```

For v1, the weights are:

| Component | Weight | Rationale |
|---|---|---|
| `w_perf` | 0.40 | Performance dominates; this is a returns-driven market |
| `w_risk` | 0.25 | Drawdown discipline is critical for capital allocators |
| `w_proof` | 0.15 | Proof validity is binary in the long run; here it's a tiebreaker for new strategies |
| `w_stake` | 0.10 | Stake weights tilt the playing field toward serious operators |
| `w_age` | 0.10 | Track-record length matters but doesn't dominate |

#### `PerformanceScore`

```
PerformanceScore(s, t) = 0.5 * NormalizedSharpe(s, 7d, c)
                       + 0.3 * NormalizedSharpe(s, 30d, c)
                       + 0.2 * NormalizedSharpe(s, 90d, c)

NormalizedSharpe(s, w, c) = (Sharpe(s, w) - median(Sharpe of class c, w))
                            / (IQR(Sharpe of class c, w))
```

Sharpe is computed from realized trade P&L only, not unrealized mark-to-market. Annualized.

#### `RiskScore`

```
RiskScore(s, t) = 1.0 - clip(MaxDrawdownBps(s, 90d) / 5000, 0, 1)
```

A strategy with no drawdown scores 1.0; one with 50% drawdown scores 0.0. Linear in between.

#### `ProofScore`

```
ProofScore(s, t) = ValidProofs(s) / TotalProofAttempts(s)
```

Pure ratio. A strategy with 1000 attempts and 999 valid scores 0.999. One failure costs ~0.001. Severe and unforgiving. After the 30th day, this should be effectively 1.0 for any well-implemented strategy.

#### `StakeScore`

```
StakeScore(s, t) = log(1 + Stake(s) / 1000) / log(1 + max(Stake of class c) / 1000)
```

Logarithmic to avoid runaway dominance by very large stakes.

#### `AgeScore`

```
AgeScore(s, t) = clip((TradesAttested(s) / 1000) ^ 0.5, 0, 1)
```

A strategy reaches max age score after ~1000 attested trades. Square-root curve so early growth is rewarded.

#### Worked example

A momentum strategy `s` of class `c` against a 2-strategy cohort. Per-window cohort Sharpes for `c` are `{1.0, 2.0}` so each window has `median = 1.5`, `IQR = 1.0` (small-cohort range proxy — IQR is undefined for `n < 4`). `s`'s raw inputs:

| Input | Value |
|---|---|
| Sharpe(s, 7d) | 2.5 |
| Sharpe(s, 30d) | 2.0 |
| Sharpe(s, 90d) | 1.8 |
| MaxDrawdown(90d) | 1500 bps (15%) |
| ValidProofs / TotalAttempts | 199 / 200 |
| Stake(s) | $5,000 |
| max(Stake of class c) | $50,000 |
| TradesAttested(s) | 250 |

Component-by-component:

```
NormalizedSharpe(7d)  = (2.5 - 1.5) / 1.0 = 1.000
NormalizedSharpe(30d) = (2.0 - 1.5) / 1.0 = 0.500
NormalizedSharpe(90d) = (1.8 - 1.5) / 1.0 = 0.300

PerformanceScore = 0.5·1.000 + 0.3·0.500 + 0.2·0.300 = 0.710
RiskScore        = 1.0 - clip(1500 / 5000, 0, 1)     = 0.700
ProofScore       = 199 / 200                          = 0.995
StakeScore       = log(1 + 5000/1000) / log(1 + 50000/1000)
                 = log(6) / log(51)                   ≈ 0.4557
AgeScore         = sqrt(250 / 1000)                   = 0.500

ReputationScore  = 0.40·0.710 + 0.25·0.700 + 0.15·0.995
                 + 0.10·0.4557 + 0.10·0.500
                 ≈ 0.7038
```

The on-chain `currentScore` is stored as `int256` in e4 fixed point (`score × 10_000`), giving `currentScore = 7038`. The reputation engine also derives `componentsHash = keccak256(abi.encode(int256, uint256, uint256, uint256, uint256))` over the five sub-scores in e4 form — this hash is recorded alongside the aggregate score by `ReputationAnchor` v2 (Phase 2 / WS3.A typehash bump) so allocators can verify the breakdown that produced any score.

**Cold-start variant.** For a freshly-registered strategy of the same class with `TradesAttested = 0` and the same `$5,000` stake, the §8.7 stake-only floor zeroes every component except `StakeScore`:

```
PerformanceScore = 0     RiskScore = 0     ProofScore = 0     AgeScore = 0
StakeScore       = log(1 + 5000/1000) / log(1 + 50000/1000) ≈ 0.4557

ReputationScore  = w_stake · StakeScore = 0.10 · 0.4557 ≈ 0.0456 → currentScore = 456
```

Bounded above by `w_stake = 0.10` regardless of stake size — a richer cold-start operator with `$50,000` stake floors at `0.10 · 1.0 = 0.1000`. This is the floor that makes the score monotonically non-decreasing as proofs accumulate (no "score went down because I have proofs now" surprises, per §8.7).

This example is the canonical reference for `services/reputation/tests/test_score_822.py`. Any change to the formulas above must update the test in lockstep (and vice versa).

### 8.3 What the allocator does with the score

Each allocator agent has its own ranking function that *consumes* the reputation score. **Helios Sentinel's** reference ranking is deliberately simple and legible:

```
Rank(s, user) = ReputationScore(s) * CapacityFactor(s)
                * FeeFactor(s, user.maxFeeRateBps)
                * ClassFitFactor(s, user.allowedStrategyClasses)

CapacityFactor(s) = max(0, 1 - currentAllocations(s) / maxCapacity(s))
FeeFactor(s, maxFee) = 1 if s.feeRate <= maxFee, else 0
ClassFitFactor(s, allowedClasses) = 1 if s.declaredClass in allowedClasses, else 0
```

Then the allocator picks the top-K strategies (where K = `min(user.maxStrategiesCount, eligibleStrategies)`) and allocates capital weighted by rank, subject to `user.maxPerStrategyBps` per strategy.

The fact that *the allocator* applies the ranking — not the registry — is what makes Helios a market: third-party allocators can use entirely different ranking functions and compete to deliver better user outcomes.

### 8.4 Anti-gaming mechanisms

A reputation system that drives real capital is a juicy target. Helios's defenses:

| Attack | Defense |
|---|---|
| **Wash trading to inflate volume** | Volume not in the score formula; only realized P&L matters |
| **Hot-hand fraud (cherry-pick winners)** | All trades must be attested; can't selectively report only winners |
| **Strategy class lying (claim momentum, do anything)** | ZK proof binds every trade to declared class; impossible to lie undetected |
| **Sybil farming (many small strategies)** | Stake-weighting + log curve makes 100 small strategies dominated by one large one |
| **Pump-and-dump on illiquid pairs** | Asset universe constrained per strategy; allocator's `allowedAssets` filters further |
| **Long-tail blowup (small wins for 30 days, blow up day 31)** | Drawdown penalty + min-stake means blow-up costs the operator their stake |
| **Front-running other strategies' trades** | Trades attest size, allocator address, and time window; cross-strategy front-running detectable |
| **Bribery of the reputation signer** | v1 limitation, addressed in roadmap (multi-sig → ZK-attested computation) |

### 8.5 What's deliberately not in v1

- **Inter-strategy correlation.** Two strategies with high correlation should arguably be allocated less aggregate capital. v1 ignores this; v2 adds correlation-aware allocation in the allocator's ranking function.
- **Time-varying weights.** The `w_*` weights are fixed in v1. v2 might let the protocol adjust them based on market regime (e.g., increase `w_risk` during high-volatility periods).
- **Slippage attribution.** A strategy that consistently gets bad fills (because of MEV or thin liquidity) takes a P&L hit but no extra reputation penalty. v2 separates skill from execution quality.
- **Capital-aware Sharpe.** A strategy that performs well on $10k but degrades on $1M (capacity-constrained) currently gets the same Sharpe per allocation. v2 should track capacity-adjusted performance.
- **Stake-stripped (pure-skill) sub-rank.** v1's reputation includes `StakeScore`, which advantages capital-rich operators (§8.1). The log curve blunts but does not eliminate this. v2 can publish a stake-stripped score alongside the canonical one so allocators and users can pick the rank function that matches their risk tolerance — capital signal vs. pure skill signal.

These are documented as known limitations and laid out in the post-hackathon roadmap. The judges should see them as *evidence of mature thinking*, not as gaps.

### 8.6 The Reputation Engine implementation

The engine is a Python service that:

1. Polls Goldsky every 60 seconds for new attested trades, NAV updates, stake changes.
2. Maintains an in-memory rolling window of trade events per strategy (with disk persistence to Postgres).
3. Recomputes scores on a 5-minute cadence (faster on event-driven triggers like large drawdowns).
4. Posts updates to `ReputationAnchor.postReputationUpdate()` signed by the Helios reputation signer.
5. Emits a public WebSocket feed of score changes for the dashboard.

Code is open-source from day one. Anyone can run their own instance against the same Goldsky subgraph and verify the outputs match.

### 8.7 Cold-start mechanism

A new strategy enters with no track record: low `PerformanceScore`, low `AgeScore`, and — for a brand-new class — undefined cohort statistics. Without an explicit bootstrap path this is a deadlock: a new strategy can't attract capital, so it can't generate the attested track record that would raise its score. Helios's cold-start has three components:

1. **Cohort-size fallback.** If a class has fewer than 3 strategies with at least 7 days of history, `NormalizedSharpe` falls back to raw Sharpe (median = 0, IQR = 1) instead of cohort scaling. This avoids degenerate median/IQR computation and lets the first few strategies in a new class receive non-zero performance signal. Implemented in the engine; `min_cohort_size = 3` is documented in `docs/reputation-math.md`.

2. **Exploration budget in the reference allocator.** Helios Sentinel reserves a configurable share of capital (default 10%, exposed in the meta-strategy as `bootstrap_share_bps`) for strategies with fewer than `min_attested_trades` (default 50). Within the bootstrap pool, allocations are stake-weighted with a flat performance prior so a new strategy gets a deterministic on-ramp without forcing the user to lower the main filter bar (e.g., a meta-strategy still gates the main 90% on Sharpe ≥ 1.5 and stake > $5k while letting the bootstrap 10% explore). Allocators that don't expose a bootstrap pool are valid market participants — they just compete for non-bootstrap capital. Helix (§11.4) ships its own variant.

3. **Stake-only score floor.** A registered strategy with no trade history scores `ReputationScore = w_stake · StakeScore` (other components zeroed), giving it a non-zero starting point bounded below by its committed stake. This makes the score monotonically non-decreasing as proofs accumulate (no "score went down because I have proofs now" surprises) and gives operators a predictable floor to plan against.

The example meta-strategy in §10 documents `bootstrap_share_bps` as a first-class field. The cold-start mechanism is part of why Helios sells stake-weighting as a tradeoff (§8.1) rather than pure positive: stake is the new strategy's only initial signal, so for the cold-start path stake *is* the rank.

---

## 9. The ZK strategy attestation system

This is the technically hardest and most differentiated component of Helios. It's also where the project earns the right to call itself "trustless" — every other reputation system in crypto is either based on unverified claims or assumes honest reporting.

### 9.1 What we're proving

A strategy agent declares its class at registration: `momentum_v1`, `mean_reversion_v1`, `yield_rotation_v1`, etc. Each class corresponds to a Circom circuit that defines what trades are *valid* for that class.

For each trade, we want to prove on-chain that the trade respects the strategy class's invariants — *without revealing the underlying signal computation, parameter values, or position sizing logic* (which are the operator's IP).

### 9.2 The chosen approach: post-trade invariant proofs

Two design options were considered:

**Option A: Full computation proofs.** Prove that the trade is the *exact* output of running the strategy's signal function on committed inputs. Maximum trustlessness, but circuit complexity is enormous (signal computation + size logic + entry/exit conditions all in-circuit). For momentum on minute bars, we estimate 100k–300k constraints, ~30s proof time. Too slow for a real trading system.

**Option B: Post-trade invariant proofs.** Prove that the trade *satisfies the class's invariants* — the trade direction matches what the signal would dictate (without proving how the signal was computed), the size respects declared bounds, the asset is in the allowed universe, the slippage is within bound, the time window is respected. ~10k–30k constraints, ~1-2s proof time. Acceptable for trading.

We're going with **Option B**. The honest tradeoff: a malicious operator could in principle construct a signal that always says "long" and always passes the invariants. But:

- The reputation system penalizes this within days (a strategy that's always long will perform terribly during downturns and lose reputation).
- The stake gets slashed if the strategy violates declared invariants (which it can't, by construction).
- The cost of running such a degenerate strategy (stake + gas + lost reputation) exceeds any rational gain.
- The strategy's parameters (signal threshold, max position size, slippage cap, stop-loss) are committed in the manifest at registration via `paramsHash` (§9.3) and bound into every proof's public inputs. The operator cannot pick a threshold that fits each individual trade — the threshold is fixed across all trades under that manifest, and rotating it requires a public, observable `StrategyRegistry.rotateParams` call with cooldown. A degenerate threshold (e.g., set so any signal triggers) is therefore visible to every allocator before any capital is risked, and weighed against the operator's reputation in the open.

The system isn't fully trustless against the strategy operator's intentions — it's trustless against the strategy operator's *capacity to misbehave under cover of class membership*. That's the meaningful guarantee.

The README will be very explicit about this tradeoff. Honesty about cryptographic guarantees is part of what makes a project credible.

### 9.3 Circuit specification: `momentum_v1`

The circuit proves the following invariants for a single trade:

**Public inputs (14 signals):**

```
1.  trade_hash             // Poseidon over trade calldata + parameter slots
2.  declared_class         // Poseidon([int.from_bytes("momentum_v1","big")])
                           //   — pinned in contracts/src/ClassIds.sol.
                           //   keccak256 lands above the BN254 field
                           //   and would fail the verifier's checkField.
3.  strategy_vault         // address as uint160 — binds proof to a specific vault
4.  params_hash            // Poseidon(signal_threshold, max_position_size,
                           //   max_slippage_bps, stop_loss_price) — committed
                           //   in the StrategyManifest at registration; once
                           //   the operator calls StrategyRegistry.commitInitialParamsHash,
                           //   the registry's paramsHashOf(strategyVault) becomes
                           //   the canonical value and the manifest hash is
                           //   only used as a Phase-1 fallback (§6.5).
5.  allocator              // uint160
6.  asset_in_idx           // index into manifest.assetUniverse
7.  asset_out_idx          // index into manifest.assetUniverse
8.  amount_in              // uint256
9.  min_amount_out         // uint256, slippage bound
10. trade_direction        // 0 = exit, 1 = enter long, 2 = enter short
11. nonce                  // replay protection
12. block_window_start     // execution must be within this window
13. block_window_end
14. oracle_root            // Poseidon root of the price-snapshot chain
```

`StrategyVault.executeWithProof` rejects any proof whose `params_hash` does not match `_activeParamsHash()` — the registry-committed value (`StrategyRegistry.paramsHashOf(strategyVault)`) when present, falling back to `manifest.paramsHash` only for vaults that haven't yet committed (Phase-1 deployment path). It also rejects proofs whose `oracle_root` is not the most-recent root anchored by `OraclePriceAnchor` within an acceptable freshness window, and whose `strategy_vault` is not the calling vault address. The verifier itself is also class-checked against `declared_class`.

The two-phase rotation API (`initiateParamsRotation` → cooldown → `completeParamsRotation`, emitting `ParamsRotated`) is the *only* path that mutates the canonical `params_hash`. There is no path on the vault, the registry, or the manifest that lets the operator silently change the committed parameters between trades — see §6.5 for the cooldown semantics and §8.7 for how the reputation engine resets `AgeScore` and `PerformanceScore` when a rotation lands.

**Witness (private to the prover):**

```
1. price_observations      // committed price array (last N bars)
2. position_state          // current position size and direction
3. signal_threshold        // operator's committed threshold (matches params_hash)
4. max_position_size       // operator's committed size cap (matches params_hash)
5. max_slippage_bps        // operator's committed slippage cap (matches params_hash)
6. stop_loss_price         // operator's committed stop-loss (matches params_hash)
7. signal_computation_data
```

**Constraints (informal):**

```
0. Poseidon(signal_threshold, max_position_size, max_slippage_bps, stop_loss_price)
   == params_hash       // operator parameters bind to the manifest commitment
1. asset_in_idx and asset_out_idx must be in the strategy's manifest asset universe
2. amount_in must be <= max_position_size
3. min_amount_out must respect max_slippage_bps (e.g., 50 bps)
4. price_observations must Poseidon-hash to oracle_root
5. If trade_direction == 1 (long entry):
   - Last N-period return of asset_out must be > signal_threshold
   - position_state must be flat or net short before this trade
6. If trade_direction == 2 (short entry): symmetric
7. If trade_direction == 0 (exit): signal-flip OR price < stop_loss_price
8. block_window_end - block_window_start must be <= 100 (no infinite window)
```

The circuit does **not** reveal the operator's specific `signal_threshold` value (that stays in the witness), but Constraint 0 plus the on-chain `params_hash == manifest.paramsHash` check together prove that the threshold *exists, was committed in the manifest before any of these trades were observed, and is identical across every trade under that manifest*. This forecloses the "pick a threshold that fits the trade" attack: an operator who wants to retune their threshold must publicly call `StrategyRegistry.rotateParams` (cooldown-gated, emits `ParamsRotated`), creating an observable break in the track record that the reputation engine and allocators see before the next trade. Same construction applies to `mean_reversion_v1`; `yield_rotation_v1` binds `signal_threshold` and `bridging_cost` directly through `trade_hash` checked against the manifest's stored hash on-chain (§9.4).

**Complexity (built, not estimated).** Per-class budget: ≤20k constraints for directional classes (momentum, mean-reversion), ≤15k for yield-rotation. Current builds: **5.4k constraints (momentum)**, **5.7k (mean-reversion)**, **6.6k (yield-rotation)** — well inside both budgets and safely under the PTAU 16 ceiling (65k) per §9.5. Proof generation ~1.5s on commodity VPS. Verifier gas cost ~250k.

### 9.4 Other strategy classes

Each class has its own circuit. The MVP ships:

- **`momentum_v1`** — as specified above. Directional spot circuit. **14 public inputs**, ~5.4k constraints (28% of the 20k circuit budget).
- **`mean_reversion_v1`** — proves trade direction matches an N-sigma deviation-from-mean signal computed in-circuit (`Σ(16·p_i − Σp)²`). **Same 14-PI layout as `momentum_v1`** so `StrategyVault.PI_*` indices and the verifier adapter's `_PUBLIC_INPUT_COUNT = 14` are reused unchanged. The witness adds `n_sigma_x100`, `is_signal_flip`, and `is_stop_loss` (the circuit asserts `is_signal_flip + is_stop_loss = is_exit` to bind the exit reason). ~5.7k constraints (29% of the 20k budget).
- **`yield_rotation_v1`** — *structurally distinct* from the directional classes. **9 public inputs** (`trade_hash, declared_class, M_from, M_to, amount_rotating, yield_oracle_root, allocator, nonce, block_window_end`). Proves: the trade rotates capital from `M_from` to `M_to`; both `(M_from, apy_from)` and `(M_to, apy_to)` are Poseidon-Merkle members of `yield_oracle_root` (depth 6 = 64 markets); both `M_from` and `M_to` are members of a private `markets_allowlist_root` (depth 4 = 16 markets) bound through `trade_hash` so the on-chain side rejects any trade whose hash doesn't match `Poseidon(StrategyRegistry.marketAllowlistRoot(class), …public fields…)`; `apy_to − apy_from ≥ signal_threshold + bridging_cost` (all in bps); `M_from ≠ M_to`; `amount_rotating > 0`. There is no `params_hash` PI slot — `signal_threshold` and `bridging_cost` bind through `trade_hash` checked against the manifest's stored hash on-chain. ~6.6k constraints (44% of the 15k budget).

Each class circuit is open-source. New classes can be added permissionlessly post-hackathon by anyone who writes a Circom circuit and submits it to a class registry (out of scope for v1).

The diversity of proof types is deliberate. Momentum and mean-reversion are both directional spot strategies with similar circuit shapes; yield-rotation introduces a fundamentally different invariant set (rate-differential proofs against a yield oracle, no directional component). This tests the multi-class registry against substantively different circuit complexity, not just three flavors of the same proof.

### 9.5 Trusted setup

The MVP uses a **local Powers of Tau ceremony** (PTAU 16, supports up to 65k constraints). This is acknowledged as suboptimal — production should use a real ceremony like Hermez or organize a Helios-specific ceremony. Documented as a known limitation in the README and in the security section.

### 9.6 Oracle commitment

Trades reference price observations. To prove a momentum signal triggered, the prover needs verified historical prices. The MVP uses a simple approach: a price oracle service signs price snapshots at each bar (1-minute), the strategy agent commits to a chain of recent snapshots via Poseidon, and the circuit verifies the snapshot-chain matches a recently-committed root.

For the reference implementation, the price oracle is operated by Helios (a known centralization point). Post-hackathon, this becomes a Chainlink/Pyth-backed adapter.

### 9.7 Proof generation flow

```
Strategy Agent:
  1. Detects signal trigger
  2. Constructs trade spec (assets, amounts, direction, etc.)
  3. POST /prove to Prover Service with:
     - witness inputs (private data)
     - public inputs (trade hash, class, etc.)
  4. Prover Service:
     - Loads class-specific circuit (.wasm + .zkey)
     - Generates Groth16 proof
     - Returns { proof, publicSignals }
  5. Strategy Agent calls StrategyVault.executeWithProof(proof, publicInputs, calldata)
  6. StrategyVault calls TradeAttestationVerifier.verify(class, proof, publicInputs)
  7. If valid, executes trade calldata (e.g., swap router call)
  8. Emits TradeAttested event
```

Latency budget: signal-to-execution ~3 seconds (1.5s for proof, 1s for tx propagation, 0.5s for inclusion). Acceptable for minute-bar strategies; insufficient for HFT (which is intentionally not in scope).

---

## 10. The Strategy Agent SDK

The SDK is a public deliverable — it's how third-party operators ship their strategies into Helios. It's also the deliverable that turns Helios from "an app" into "an ecosystem."

### 10.1 SDK package

```
pip install helios-strategy-sdk
```

(Python is the primary language because the quant ecosystem speaks Python. A TypeScript SDK ships post-hackathon if there's demand.)

### 10.2 The minimal strategy implementation

```python
from helios import StrategyAgent, MarketSnapshot, TradeIntent, Direction

class MyMomentumStrategy(StrategyAgent):
    declared_class = "momentum_v1"
    asset_universe = ["BTC", "ETH", "SOL", "BNB"]
    max_position_size_usd = 10_000
    fee_rate_bps = 2000  # 20%

    def __init__(self):
        super().__init__()
        self.signal_threshold = 0.015  # 1.5% return triggers signal
        self.lookback_bars = 10

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        recent_return = snapshot.return_over(bars=self.lookback_bars)

        if recent_return > self.signal_threshold and self.position_for(asset) <= 0:
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_usd=min(5000, self.available_capital * 0.5),
                direction=Direction.LONG,
                max_slippage_bps=30,
            )

        if recent_return < -self.signal_threshold and self.position_for(asset) > 0:
            return TradeIntent(
                asset_in=asset,
                asset_out="USDC",
                amount_in_asset=self.position_for(asset),
                direction=Direction.EXIT,
                max_slippage_bps=30,
            )

        return None
```

That's it. The SDK handles:

- Polling market data (one-minute bars from configured providers)
- Calling `on_bar` for each asset on each bar
- Constructing the trade calldata for the chosen DEX router
- Bundling the witness data and calling the Prover Service
- Submitting `executeWithProof` with proper gas handling
- Tracking NAV, position state, and P&L
- Reporting NAV to StrategyVault on cadence
- Claiming accrued fees on `distributeRealized` events

### 10.3 SDK features

- **Backtesting harness.** `helios backtest --strategy ./my.py --period 90d --capital 10000` runs the strategy against historical data with full P&L, drawdown, and Sharpe reporting.
- **Local simulator.** `helios simulate` runs the strategy against a mocked-up market; useful for CI.
- **Deployment helpers.** `helios deploy` packages the strategy as a Docker image, configures Kite Passport identity, and bootstraps the strategy on a target VPS.
- **Stake management.** `helios stake top-up --amount 1000` posts additional stake.
- **Proof testing.** `helios test-proof --trade <spec>` runs a full proof generation cycle locally to verify circuit compatibility.

### 10.4 Documented strategy classes (v1)

For the hackathon, we ship documentation for three classes. Each comes with:

- A formal specification of the class invariants
- The Circom circuit source
- A reference Python implementation
- A backtest report on 90 days of historical data

Operators can implement their own variants of these classes. They cannot invent new classes in v1 (post-hackathon: a permissionless class registry with circuit-submission gating).

---

## 11. The Allocator Agent

The allocator is the autonomous capital router — the second-most-important agent class in Helios after strategy agents. The MVP ships **Helios Sentinel** as the reference allocator and **the AllocatorSDK** as a public v1 deliverable so third parties can ship competing allocators from day one. A second reference allocator is also seeded for the demo to show the marketplace mechanism live.

### 11.1 Allocator responsibilities

Every allocator (Sentinel or third-party) must perform six functions:

1. **Strategy selection.** Given a user's meta-strategy, query the registry for eligible strategies and rank them.
2. **Capital deployment.** Issue sub-delegations from AllocatorVault to selected StrategyVaults, respecting per-strategy and total caps.
3. **Drawdown enforcement.** Continuously monitor each strategy's NAV against the per-allocation HWM. Trigger defunds the moment the user's drawdown threshold is breached.
4. **Periodic rebalancing.** On the user's `rebalanceCadenceSec` cycle, recompute target allocation and migrate capital.
5. **Fee crystallization.** Trigger `settleStrategyFee` when NAV exceeds HWM by a configurable threshold.
6. **User communication.** Emit events that the dashboard activity rail consumes (and that the post-hackathon Telegram bot will fan out — see §17).

The *what* (these six functions) is shared. The *how* (especially the ranking function) is where allocators compete.

### 11.2 Helios Sentinel — the reference decision loop

Sentinel ships a deliberately legible, conservative reference loop. It's not the most sophisticated possible allocator — it's the *baseline that demonstrates the mechanism cleanly*. Competing allocators are expected to outperform it on user outcomes.

```python
async def sentinel_loop(user_id):
    user = load_user_meta_strategy(user_id)
    while user.active:
        # Step 1: Discover and rank
        candidates = goldsky.query_strategies(
            allowed_classes=user.allowed_strategy_classes,
            allowed_assets=user.allowed_assets,
            min_reputation=user.min_reputation,
            max_fee_bps=user.max_fee_rate_bps,
        )
        ranked = sorted(
            candidates,
            key=lambda s: sentinel_rank_score(s, user),  # see Section 8.3
            reverse=True,
        )

        # Step 2: Carve out the cold-start bootstrap pool (§8.7) before main ranking
        bootstrap_capital = (user.allocated_capital * user.bootstrap_share_bps) // 10_000
        main_capital = user.allocated_capital - bootstrap_capital

        bootstrap_candidates = [
            s for s in candidates
            if s.trades_attested < user.min_attested_trades
        ]
        main_candidates = [s for s in ranked if s not in bootstrap_candidates]

        # Step 3: Compute target allocation — main pool by rank, bootstrap pool stake-weighted
        target_main = compute_target_allocation(
            main_candidates,
            total_capital=main_capital,
            max_per_strategy_bps=user.max_per_strategy_bps,
            max_strategies=user.max_strategies_count,
        )
        target_bootstrap = stake_weighted_allocation(
            bootstrap_candidates,
            total_capital=bootstrap_capital,
            max_per_strategy_bps=user.max_per_strategy_bps,
        )
        target = merge_targets(target_main, target_bootstrap)

        # Step 4: Diff against current
        current = load_current_allocations(user_id)
        diff_ops = diff_allocations(current, target)

        # Step 5: Drawdown check (highest priority)
        for alloc in current:
            nav = load_nav(alloc.strategy)
            dd = (alloc.hwm - nav) / alloc.hwm
            if dd > user.drawdown_threshold:
                emit_defund(user_id, alloc.strategy, reason="DRAWDOWN_BREACH")
                continue

        # Step 6: Apply diffs (skip during drawdown enforcement)
        for op in diff_ops:
            if op.kind == "ADD":
                emit_allocate(user_id, op.strategy, op.amount)
            elif op.kind == "INCREASE":
                emit_increase(user_id, op.strategy, op.delta)
            elif op.kind == "DECREASE":
                emit_decrease(user_id, op.strategy, op.delta)
            elif op.kind == "REMOVE":
                emit_defund(user_id, op.strategy, reason="RANK_DROP")

        # Step 7: Fee crystallization
        for alloc in current:
            nav = load_nav(alloc.strategy)
            if nav > alloc.hwm * (1 + FEE_THRESHOLD):
                emit_settle_fee(user_id, alloc.strategy)

        # Step 8: Sleep
        await sleep_until_next_cycle(user)
```

Sentinel runs on multiple cadences:

- **Drawdown check:** every 60s (the most time-sensitive)
- **Rank update:** every 5 minutes
- **Rebalancing decision:** per user's `rebalanceCadenceSec`
- **Fee crystallization:** opportunistic, on each cycle

The Sentinel ranking function is in Section 8.3. It is intentionally simple: weighted reputation × capacity × fee-fit × class-fit. No correlation awareness, no regime detection, no ML. This makes it the obvious baseline for competing allocators to beat.

### 11.3 The AllocatorSDK (v1 deliverable)

The AllocatorSDK is a public Python package that lets anyone deploy a competing allocator. It ships as a v1 deliverable because the marketplace mechanism is hollow without competition — a network with one allocator is just a fancy bot, not a market.

```
pip install helios-allocator-sdk
```

**The minimal allocator implementation:**

```python
from helios_allocator import BaseAllocator, MetaStrategy, StrategyCandidate, AllocationTarget

class MyVolAdjustedAllocator(BaseAllocator):
    name = "VolatilityAware"
    fee_rate_bps = 500  # 5% on user net realized profit above HWM
    supported_classes = ["momentum_v1", "mean_reversion_v1", "yield_rotation_v1"]

    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        """Return a score per candidate. Higher = better."""
        scores = []
        for c in candidates:
            base = c.reputation_score * c.capacity_factor * c.fee_fit(user.max_fee_rate_bps)
            vol_penalty = 1.0 / (1.0 + c.realized_volatility_30d * 5.0)
            scores.append(base * vol_penalty)
        return scores

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        """Convert a ranked list into concrete capital allocations."""
        return self.default_top_k_allocation(
            user, ranked, capital,
            correlation_aware=True,  # SDK helper
            max_correlation=0.7,
        )
```

That's the complete surface an allocator operator must implement. The SDK handles:

- User onboarding (reading meta-strategies from `UserVault`, validating constraints)
- Drawdown monitoring at 60s cadence
- Fee crystallization at HWM thresholds
- Defund and rebalance transaction submission as userOps from the allocator's registered EOA
- Goldsky integration for strategy discovery and reputation reads
- ReputationAnchor integration for allocator's own reputation score
- WebSocket event emission for dashboards/bots
- Stake management and slashing handling
- Local backtesting harness against historical strategy P&L
- Docker packaging and deployment helpers

**SDK CLI commands:**

```
helios-allocator init                       # Scaffold a new allocator project
helios-allocator backtest --period 90d      # Run against historical strategy data
helios-allocator simulate --users 100       # Multi-user simulation
helios-allocator stake top-up --amount N    # Manage allocator stake
helios-allocator deploy --vps user@server   # Deploy as Docker container
helios-allocator logs                       # Live tail of operational events
```

**The AllocatorRegistry** (a Kite contract) holds every registered allocator's manifest: name, fee rate, supported classes, stake, reputation score, operator address. Users browsing the web app's `/allocators` page see this directory. The Sentinel listing has an "Official Reference" badge; everything else competes on its own merits.

### 11.4 Helios Helix — the second reference allocator

> **v1 scope (Helix-lite).** Helix v1 ships only `helix_fee_factor` (continuous fee-fit, regime-fixed at NORMAL) over `score_weighted_allocation` from the AllocatorSDK. The full feature set described in §11.4.1 (regime detection from BTC realized vol, correlation-aware greedy pick, regime-adaptive fee weighting) is post-hackathon Phase 1 — see §16. The AllocatorSDK still ships the `detect_regime`, `pairwise_correlation_from_goldsky`, and `btc_realized_vol_30d` hooks in v1 so any third-party allocator can adopt them earlier than Helix does. The §11.4.1 code blocks below show the *target* implementation; treat them as the v2 spec, not v1 shipping code.

For the hackathon demo, the Helios team ships **Helios Helix** alongside Sentinel as a second reference allocator. The v1 differentiation from Sentinel is a continuous fee-fit factor and `score_weighted_allocation` over a top-K-by-rank pick — enough to produce visibly different allocations on the same user's onboard, which is the demo bar. The full v2 picture (correlation awareness + regime adaptation) is the post-hackathon target.

Helix is also a branded reference name (like Sentinel) — the `AllocatorRegistry` reserves "Helios Helix" and the Helios team multi-sig holds the assignment. Third-party allocators cannot register under the `Helios *` namespace.

The demo includes a brief moment showing both allocators side-by-side: a user can pick Sentinel (default, simple) or Helix (alternative, more sophisticated), with the `/allocators` directory showing each allocator's current users, stake, reputation score, and ranking-function hash. This is the proof that Helios is a *market*, not a *product*.

Helix's existence has one more load-bearing purpose beyond the demo: it validates the AllocatorSDK from a fresh perspective. A second reference allocator, built from the SDK ground-up in under a week, is the strongest possible quality signal for the SDK itself. Third parties inspecting the repo see not just an SDK, but two concrete implementations of it working side-by-side in production.

#### 11.4.1 How Helix differs from Sentinel, concretely

Helix's differences from Sentinel live in three places:

**(a) Regime-adaptive fee-fit factor.** Sentinel's `FeeFactor` is binary: a strategy either satisfies `s.feeRate <= user.maxFeeRateBps` or it gets zero weight. Helix adds a continuous penalty that depends on the current volatility regime.

```python
def helix_fee_factor(strategy_fee_bps: int, user_max_fee_bps: int, regime: Regime) -> float:
    if strategy_fee_bps > user_max_fee_bps:
        return 0.0  # hard cap respected

    # How much fee headroom does this strategy leave?
    headroom = (user_max_fee_bps - strategy_fee_bps) / user_max_fee_bps

    # In high-vol regimes, alpha-above-fees is thinner; prefer low-fee strategies
    # In low-vol regimes, high fees are tolerable if reputation is high
    if regime == Regime.HIGH_VOL:
        return headroom ** 0.5   # favor cheaper strategies sharply
    elif regime == Regime.LOW_VOL:
        return 0.5 + 0.5 * headroom  # mild fee preference only
    else:  # NORMAL
        return 0.3 + 0.7 * headroom
```

The regime itself is computed from rolling BTC realized volatility percentile against a 1-year window:

```python
def detect_regime(btc_realized_vol_30d: float, historical_percentiles: dict) -> Regime:
    if btc_realized_vol_30d >= historical_percentiles["p80"]:
        return Regime.HIGH_VOL
    elif btc_realized_vol_30d <= historical_percentiles["p20"]:
        return Regime.LOW_VOL
    else:
        return Regime.NORMAL
```

**(b) Correlation-aware greedy allocation.** Sentinel picks the top-K candidates by raw score. Helix does a greedy pick that penalizes incremental additions whose correlation with the already-selected portfolio exceeds a threshold.

```python
def helix_greedy_pick(
    user: MetaStrategy,
    ranked: list[StrategyCandidate],
    max_pairwise_correlation: float = 0.7,
) -> list[StrategyCandidate]:
    """Greedy selection: rank-ordered, skip candidates that would spike portfolio correlation."""
    selected = []
    for candidate in ranked:
        if len(selected) >= user.max_strategies_count:
            break

        # Compute average correlation of this candidate to the currently-selected set
        if not selected:
            avg_corr = 0.0
        else:
            correlations = [
                pairwise_correlation_from_goldsky(candidate.strategy_id, s.strategy_id)
                for s in selected
            ]
            avg_corr = sum(correlations) / len(correlations)

        if avg_corr <= max_pairwise_correlation:
            selected.append(candidate)
        # else: skip this one, try the next
    return selected
```

Pairwise correlation is computed from a rolling 30-day NAV time series per strategy, available via Goldsky. The SDK exposes `pairwise_correlation_from_goldsky` as a helper so Helix doesn't have to reimplement the plumbing.

**(c) The top-level ranking function.** Helix's `rank_strategies` combines the base score with regime-aware fee factor, then the allocation pass uses correlation-aware greedy selection:

```python
class HeliosHelix(BaseAllocator):
    name = "Helios Helix"
    fee_rate_bps = 600  # 6% — slightly higher than Sentinel's 5% to account for more sophisticated logic
    supported_classes = ["momentum_v1", "mean_reversion_v1", "yield_rotation_v1"]

    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        regime = detect_regime(
            btc_realized_vol_30d=self.market_data.btc_realized_vol_30d(),
            historical_percentiles=self.market_data.btc_vol_percentiles_1y(),
        )
        scores = []
        for c in candidates:
            base = (
                c.reputation_score
                * c.capacity_factor
                * c.class_fit(user.allowed_strategy_classes)
            )
            fee = helix_fee_factor(c.fee_rate_bps, user.max_fee_rate_bps, regime)
            scores.append(base * fee)
        return scores

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        # Step 1: correlation-aware greedy pick
        selected = helix_greedy_pick(user, ranked, max_pairwise_correlation=0.7)

        # Step 2: score-weighted allocation within the selected set,
        # subject to user.max_per_strategy_bps per strategy
        return self.score_weighted_allocation(
            user, selected, capital,
            cap_per_strategy_bps=user.max_per_strategy_bps,
        )
```

#### 11.4.2 Why Helix should outperform Sentinel in expectation

Both mechanisms have clean economic intuitions:

- **Regime-adaptive fees** reflect that realized alpha net of fees is a function of market conditions. Paying 30% on a smooth market is often worse than paying 10% for a passable strategy.
- **Correlation awareness** avoids the classic portfolio construction error of owning five momentum agents that are all long at the same time — which is not diversification, it's leverage.

These are well-known portfolio-theory improvements. Neither is novel *in TradFi*. What makes them interesting here is that they're implemented as a **deployable AllocatorSDK strategy** that any user can opt into or opt out of, with the allocator's own reputation tracking whether these improvements actually deliver better user outcomes over time. If Helix outperforms Sentinel across users, it will organically attract more delegations. If it doesn't, users migrate back to Sentinel. The market sorts it out.

This is the point: **Helios doesn't pick winners among allocator strategies; the market does.** Sentinel is the baseline, Helix is a candidate improvement, and third-party allocators are free to try their own ideas. The AllocatorRegistry and ReputationAnchor do the accounting.

### 11.5 Allocator reputation

Allocators have their own reputation, separate from strategy reputation. Allocator reputation is computed from:

- **Aggregate user net P&L above HWM** across all delegated capital (the dominant factor)
- **Drawdown discipline** — did the allocator actually fire bad strategies on time?
- **User retention** — do users keep capital with this allocator over time?
- **Stake size** — log-curve weighted, same approach as strategies

Allocator reputation is anchored on the same `ReputationAnchor` contract, distinguished by an `actor_type` flag. The dashboard renders allocator leaderboards alongside strategy leaderboards.

This makes Helios a *two-sided* reputation market: strategies compete to attract allocators, allocators compete to attract users, and both are scored on cryptographically verified outcomes.

---

## 12. Cross-chain architecture

Cross-chain is not bolted on. It's central to the thesis: strategy agents should trade on whichever chain has the best venue for their asset class, while the Kite registry remains the canonical identity and accounting layer.

### 12.1 Chain roles and function map

The rule: **Kite is identity + accounting + small-position execution. Base is large-position spot. Arbitrum is yield + diversified spot.** Each chain has a job that the others can't do as well — which is what makes the cross-chain story honest rather than decorative.

| Chain | Function in Helios | Why this chain |
|---|---|---|
| **Kite (2368 testnet, 2366 mainnet)** | **Canonical layer.** Holds the StrategyRegistry, AllocatorRegistry, ReputationAnchor, AllocatorVault, UserVault. All identity (Passport), allocator coordination, fee accounting, and reputation lives here. Strategies can also *execute* here — momentum and mean-reversion strategies trading WKITE / USDC.e / WETH on the **Algebra Integral** concentrated-liquidity DEX. Bridged USDC.e and USDT (Lucid Labs) provide stablecoin settlement; Lucid bridge controllers connect to Avalanche and Celo. | Kite is the only chain with the **Passport-issued ERC-4337 smart-account stack + paymaster + x402** we lean on for one-passkey onboarding, gasless strategy execution, and the agent-economy demo beat. The Algebra DEX gives us a real (if small-cap) execution venue. The native KITE token gives us native gas economics. The 1-second block times help the auto-defund moment fire crisply during the demo. **Kite has no native perp DEX** — only spot via Algebra — which is why the v1 strategy classes are spot/yield-only (perps deferred to roadmap; see Section 17). |
| **Base (8453 mainnet, 84532 Sepolia testnet)** | **Deep-liquidity spot execution.** Strategy agents trading large-cap pairs (ETH/USDC, WBTC/USDC, SOL/USDC) on **Uniswap V4 hooks**. This is where momentum and mean-reversion strategies that need real liquidity for $10k+ position sizes execute. Per-chain TradeAttestationVerifier deployments verify Groth16 proofs locally; trade attestations and NAV deltas batch back to Kite via LayerZero OApp. | Base has the **deepest spot liquidity** in the L2 ecosystem and Uniswap V4 is the most mature concentrated-liquidity venue. **Coinbase Ventures is the lead hackathon partner** — using Base meaningfully (not decoratively) is a narrative win. Cheap gas, fast finality, and a maturing agent-tooling ecosystem (Base Account, OnchainKit) align with our identity model. |
| **Arbitrum (42161 mainnet, 421614 Sepolia testnet)** | **Multi-protocol yield surface.** Yield rotation strategies move capital between **Aave V3, Compound V3**, and other lending markets here. Also serves as a secondary spot venue (Camelot V3, Uniswap V3) for diversification of execution venues — useful if Base experiences an outage or unusual MEV conditions. | Arbitrum has the **deepest set of mature lending markets** in the L2 ecosystem (Aave V3 alone has billions in TVL there). Yield rotation strategies need a venue with multiple competing protocols to be meaningful. The cross-chain rate differential between Arbitrum, Base, and Kite is exactly what makes `yield_rotation_v1` an economically interesting strategy class. |

#### Why these three and not others

- **Why not Solana?** No native Kite-style Passport + paymaster + x402 stack. Cross-VM bridging adds complexity beyond the demo's value.
- **Why not Optimism?** Functionally similar to Base; would add deployment surface without adding distinct capability.
- **Why not Avalanche C-Chain?** Considered, since Kite originated as an Avalanche subnet and Lucid bridge controllers run on Avalanche. Defer to post-hackathon — Avalanche becomes the natural next chain to add given the existing Lucid bridge primitives.
- **Why not BSC, given it's the obvious meme-trading chain?** Out of scope — Helios's v1 asset universe is crypto majors. BSC integration is reasonable for v2 if a meme-focused strategy class is added.

#### Passport runs on testnet — v1 uses it directly

Kite Passport supports the Kite Testnet (chain id **2368**) with the same install, passkey, and x402 flow as mainnet — the only thing that differs is the chain target. v1 ships on testnet and integrates **real Passport** end-to-end; no EIP-712 shim, no "deferred until mainnet" stub. **Mainnet promotion (chain 2366) is a stretch goal**, not a planned phase — exercised only if time permits after Phase 6 acceptance. If exercised, the mainnet cutover swaps the chain target and re-runs the demo against `chain id 2366`; nothing about the auth or payment path changes.

Testnet config (verified against `docs.gokite.ai`, 2026-05-08):

| Surface | Value |
|---|---|
| Network identifier (Passport API) | `kite-testnet` |
| Chain id | `2368` |
| RPC | `https://rpc-testnet.gokite.ai/` (WSS at `wss://rpc-testnet.gokite.ai/ws`) |
| Faucet | `https://faucet.gokite.ai` |
| Block explorer | `https://testnet.kitescan.ai/` |
| x402 facilitator | `0x12343e649e6b2b2b77649DFAb88f103c02F3C78b` |
| Test payment token used in Passport x402 examples | `0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63` |
| Live x402 sample service | `https://x402.dev.gokite.ai/api/weather` |
| Passport CLI install | `curl -fsSL https://agentpassport.ai/install.sh \| bash` |

Note on env-var naming: Passport wallets are MPC-backed and are not exposed as raw private keys on either network, so do not introduce a `*_SIGNER_PK` variable. CLAUDE.md uses `KITE_PASSPORT_SESSION_ID` for the session token plus `KITE_PASSPORT_NETWORK` (`kite-testnet` for v1; `kite-mainnet` only if the mainnet stretch is exercised) to select the chain target.

### 12.2 Cross-chain lifecycle

A strategy agent deployed on Base:

1. Strategy is registered on the Kite StrategyRegistry. The manifest declares it as a Base-deployed strategy.
2. A StrategyVault is deployed on Base (a parallel deployment of the same contract).
3. The allocator allocates capital. The allocation flow is:
   - On Kite: AllocatorVault tracks the allocation, emits `AllocationCreated` event.
   - LayerZero OApp message sent: `BridgeAndDeploy(strategy, amount)` to Base.
   - On Base: HeliosOApp receives the message, mints capital on Base's StrategyVault, executes via the bridge.
   - Strategy agent on Base sees its capital arrive, begins trading.
4. Trades execute on Base. Each trade carries a Groth16 proof. Verification is local on Base (per-chain TradeAttestationVerifier).
5. NAV updates and trade attestations are batched and posted back to Kite via LayerZero OApp messages.
6. ReputationAnchor on Kite consumes the cross-chain updates and updates the canonical reputation score.

### 12.3 Capital bridging

The MVP uses **LayerZero OFT** for the underlying capital movement. USDC must be available as an OFT (or equivalent) on all three chains. For testnet, we use a mock USDC OFT deployed across the three test networks.

For the demo, we'll keep one strategy on Kite, one on Base, and one on Arbitrum — enough to demonstrate the cross-chain flow without complicating the demo physics.

**Cost model + trajectory.** v1 ships per-(user, destination-chain) batching: a single `OFT.send` can carry N strategy allocations sharing the same destination, amortizing LZ V2's ~1 KITE fixed executor + DVN fee across the batch (cuts a 3-candidate cold-start from ~3.2 KITE to ~2.2 KITE on Kite testnet). The next layers — folding the `lzCompose` hop into the OFT adapter's `_credit` (saves ~30–40% per hop) and multi-user aggregation per (strategy, dst chain) (saves linearly with concurrent users) — are post-v1 roadmap items tracked in `docs/cross-chain-cost-roadmap.md`. The shape ships incrementally because LZ V2's fee is mostly fixed-cost, so each lever attacks a different floor.

### 12.4 Reputation propagation

Reputation propagation is one-directional (other chains → Kite). On Base/Arbitrum:

```solidity
function postCrossChainAttestation(
    address strategy,
    TradeAttestation calldata attestation
) internal {
    require(verifier.verify(...));
    emit TradeAttested(strategy, attestation);

    // Periodically, batch and forward to Kite
    if (block.number % BATCH_INTERVAL == 0) {
        bytes memory payload = abi.encode(strategy, pendingAttestations);
        endpoint.send(KITE_EID, payload, options, MessagingFee(...));
    }
}
```

Kite is the source of truth. If a Base node reports inconsistent data, the LayerZero DVN setup detects it. (The MVP uses default DVN configuration; production should use a stricter DVN set.)

### 12.5 Why this design

- **Single source of truth.** One canonical reputation score per strategy, on Kite. No syncing problem across registries.
- **Venue flexibility.** Strategies aren't restricted to chains with shallow liquidity for their asset class.
- **Honest LayerZero usage.** Reputation propagation is *meaningful* — it carries information that materially affects allocation decisions, not just "we use LayerZero" decoration.

---

## 13. Frontend and event surfaces

### 13.1 Web app

A Next.js 14 app deployed at `helios.market` (or similar). For users and auditors.

**Pages:**

| Route | Purpose |
|---|---|
| `/` | Landing — explains the thesis, shows live aggregate stats |
| `/strategies` | Public Strategy Registry — all registered strategies with rep scores, P&L history, manifest |
| `/strategies/[id]` | Strategy detail — full P&L curve, trade log, proof verifications, fees earned |
| `/allocators` | Allocator directory (future-facing; v1 shows only Helios reference) |
| `/dashboard` | User dashboard — current allocation, NAVs, fees, timeline, controls |
| `/onboard` | Meta-strategy builder — template picker, customization, signing flow |
| `/audit/[strategy]` | Auditor view — verify any strategy's reputation by replaying the math against on-chain data |
| `/docs` | Embedded docs for operators |

**Tech stack:**

- Next.js 14 (App Router), React 18, TypeScript
- TailwindCSS for styling
- wagmi v2 + viem for wallet/chain
- Recharts for P&L curves and reputation histories
- TanStack Query for data fetching from the Allocator Service and Goldsky
- Vercel deployment

**Design ethos.** Bloomberg-terminal density meets clean modern web. Information-dense for operators and serious users; the landing and onboarding flows are simpler. Borrows the visual confidence of MEFAI Terminal and the judge-evaluation-friendly clarity of SynthLaunch.

### 13.2 Activity rail (dashboard event stream)

The dashboard's persistent activity rail is the v1 event surface. It consumes the Allocator Service's WebSocket feed and prints each event as a single dense row — strategy allocations, defunds, rebalances, fees accrued, withdrawals ready. The same five event types that v2's Telegram bot will fan out (see Phase 1 post-hackathon roadmap, §17) drive the rail today; the formatting rules in `DESIGN.md §15` (≤200 chars, one event per row, restrained ⚡/⚠️/✓ status markers, Kitescan/BaseScan/Arbiscan trade links) apply to rail rows verbatim. During the demo, judges see the cascade and the auto-defund land in the activity rail in real time, with no second device or notification surface required.

A standalone Telegram bot (`@helios_market_bot`) is deferred to post-hackathon Phase 1 — see §17. It will subscribe to the same WS feed and reuse the §15 templates without behavioural change to the rail.

### 13.3 REST/WebSocket API

The Allocator Service exposes a public API. The web app is the v1 consumer; the deferred Telegram bot and any third-party surfaces will sit on the same endpoints.

```
GET  /v1/strategies                — list strategies with reputation, manifest
GET  /v1/strategies/{id}/trades    — historical trade log
GET  /v1/strategies/{id}/nav       — NAV history
GET  /v1/users/{user}/dashboard   — user dashboard data
WS   /v1/events                    — global event stream (allocations, defunds, fees)
```

---

## 14. Demo scenario and stagecraft

The demo is a 3-minute live walkthrough. Tight, scripted, with the auto-defund as the headline beat. Judges need to leave remembering one image: "the system fired a bad strategy by itself."

### 14.1 The 3-minute script

**[0:00–0:20] The setup.** Web app open, dashboard view. Voiceover: *"Maya wants to put $1,000 to work in AI trading agents. She doesn't want to babysit it. She doesn't want to give up custody. She wants policy guardrails. Let's see what one signature gets her."*

**[0:20–0:50] The approval.** Open the meta-strategy builder. Pick the "Balanced" template, customize asset universe to BTC/ETH/SOL. Briefly hover the allocator selector showing Sentinel (default, "Official Reference") vs Helix (the SDK-built alternative, "Official Reference"); keep Sentinel for the demo flow. Approve via Kite Passport — one passkey prompt, no MetaMask popup. The frontend submits a single batched userOp ( `USDC.approve` + `UserVault.deposit` + `setMetaStrategy` + `delegateToAllocator`) sponsored by the paymaster. Voiceover: *"She chooses an allocator — Sentinel is the reference, but anyone can deploy their own. One passkey approval is the only thing she does. From here, everything is autonomous and on-chain."*

**[0:50–1:30] The cascade.** Dashboard updates in real-time. Show Sentinel picking 4 strategies across the three chains. Show the first ZK-attested trade landing on each. The activity rail prints each allocation as it confirms: *"⚡ Sentinel → MomentumKite-A $300", "⚡ Sentinel → MeanRevBase-B $250", "⚡ Sentinel → MomentumArb-C $250", "⚡ Sentinel → YieldRotationArb-D $200"*. Voiceover: *"Each trade carries a ZK proof binding it to the strategy's declared class. A momentum agent literally cannot execute a yield rotation and have it count. This is the trustless layer underneath."*

**[1:30–2:10] The drawdown.** Switch the demo into "scenario mode" (deterministic market replay — see 14.2). MomentumKite-A's NAV starts dropping. Dashboard's drawdown indicator flashes amber, then red. At -15%: the activity rail prints two rows in sequence: *"⚠️ MomentumKite-A defunded at -15.2%"* and *"⚡ MeanRevArb-E ← reallocated $300"*. Sentinel pulls capital, reroutes to the next-best-ranked strategy. Dashboard shows the migration happen in real-time. Voiceover: *"This is the headline behavior. No human pressed a button. Sentinel saw the threshold breach, defunded the bad strategy, and rerouted capital — autonomously, in 12 seconds. If Sentinel itself had gone offline, anyone could trigger the same defund: it's enforced on-chain."*

**[2:10–2:40] The cross-chain reputation.** Show MomentumArb-C landing a profitable trade on Arbitrum. Reputation update flows from Arbitrum → Kite via LayerZero. Dashboard's strategy ranking updates; MomentumArb-C climbs two positions. Voiceover: *"Strategies trade where venue is best — momentum where liquidity is deep, yield rotation where lending rates compete. Reputation lives canonically on Kite. LayerZero stitches it together so a track record earned on Arbitrum becomes capital on Kite, instantly."*

**[2:40–3:00] The audit close.** Switch to Kitescan. Show the verified contracts. Show a TradeAttested event with the proof signals. Voiceover: *"Every claim is verifiable on-chain. Helios is open infrastructure for the agentic economy — the first capital market where AI traders earn capital by performance, lose it by failure, and operate under cryptographic constraints. Built on Kite. Powered by ZK. Cross-chain by design."*

### 14.2 Demo stagecraft

**Scenario mode.** The demo runs against a deterministic market replay so the auto-defund triggers reliably during the live presentation. This is **not cheating** — the mechanism is real, the on-chain transactions are real, the proofs are real. What's curated is the *market scenario* used to trigger the behavior. The README clearly distinguishes "live mode" (real market data) from "scenario mode" (replayed historical data) and ships both. Judges can run either.

**Pre-demo state.** Before the demo, we pre-deploy all contracts (Kite, Base, Arbitrum), pre-fund Maya's wallet with $1,000 USDC, pre-register at least 6 strategies (4 initial allocation targets + 2 reserve candidates for post-defund reallocation), pre-deploy strategy agents on the VPS, pre-register Sentinel and Helix on `AllocatorRegistry`. The demo starts from a clean dashboard but a warm system. This is standard hackathon practice and what every winner we studied did.

**Backup demo video.** A pre-recorded 90-second version exists for fallback if anything fails live. Submitted alongside the live demo.

**The judge quick-eval link.** `helios.market/judge` — a single page that gives judges everything: video link, live URL, contract addresses on Kitescan, GitHub links, 5-minute eval checklist.

---

## 15. Security, trust, and threat model

A protocol that handles capital must articulate its trust model honestly. This section is what mature judges (and serious users) will read first.

### 15.1 Trust assumptions

| Component | Trust required | Why |
|---|---|---|
| User's Passport identity | **Trust Particle Network MPC** (the EOA backing the AA wallet is an MPC share, not a hardware-held key) | Documented limitation; v2 considers a self-custody migration path once `gokite-aa-sdk` exposes a "claim ownership to external EOA" flow |
| Kite Passport infrastructure | Trust `@gokite-network/auth` + `gokite-aa-sdk` + Kite's EntryPoint and SmartAccountFactory contracts | Inherits Kite's security model and Particle Network's MPC security model |
| Strategy operator | **Limited trust** — they can't violate class invariants (ZK-enforced) but they can run a strategy that loses money | The economic model handles this: bad strategies lose reputation and capital |
| Allocator operator | **Limited trust** — they can't violate user's meta-strategy (on-chain enforced) but they can rank suboptimally | Multiple allocators allow market competition |
| Reputation Engine signer | **Trusted** in v1 (single signer); **trust-minimized** in v2 (multi-sig); **trustless** in v3 (ZK-attested computation) | Documented limitation with clear roadmap |
| Price oracle | **Trusted** in v1 (Helios-operated); **trust-minimized** in v2 (Chainlink/Pyth). Load-bearing for both ZK proof validation (`oracle_root`) and the auto-defund TWAP trigger — see threat-model entry in §15.2. | Documented limitation |
| Yield-market allowlist | **Trusted** in v1 — `StrategyRegistry.setMarketAllowlistRoot` is owner-only (Helios multi-sig); v2 path is per-class governance | A malicious allowlist could whitelist an unaudited Aave fork; honest framing is "Helios curates the lending venues for `yield_rotation_v1` in v1" |
| NAV divergence threshold | **Trusted** in v1 — the 5% slashable-divergence threshold is owner-set; the `slash` call itself is `onlyRegistry` and routes through the Helios multi-sig | Threshold change requires a multi-sig action; v2 considers per-class governance |
| LayerZero DVN set | Trust LayerZero's default DVN configuration | Standard for LayerZero apps |
| Helios trusted setup | **Trusted ceremony** in v1 (local PTAU); production needs a real ceremony | Documented limitation |

### 15.2 Threat model

**Threat: Malicious strategy operator drains user funds via class violation.**
Defense: Impossible. Trades require valid Groth16 proofs of class compliance. Invalid proof = revert.

**Threat: Malicious strategy operator runs a strategy designed to lose money slowly to grief users.**
Defense: Reputation penalty + drawdown defund. Loss is bounded by the user's drawdown threshold. Operator loses stake on slashing-trigger violations.

**Threat: Allocator misbehaves (allocates capital outside the user's meta-strategy).**
Defense: AllocatorVault on-chain enforcement reverts any allocation outside the meta-strategy bounds.

**Threat: Allocator goes offline during a market crash, fails to defund.**
Defense: `defundStrategy` is permissionless when drawdown threshold is breached. Anyone can trigger it. The auto-defund mechanism doesn't depend on a single point of failure.

**Threat: Reputation Engine is bribed to inflate a strategy's score.**
Defense: v1 limitation. Mitigated by: (a) the engine code is open-source and the inputs are public on-chain, so any inflation is detectable by re-running the math; (b) the v2 multi-sig model; (c) the v3 ZK computation.

**Threat: Helios price oracle is compromised.**
Defense: A compromised oracle is a high-impact trust failure in v1 because it controls the canonical `oracle_root` bound into every ZK proof — `OraclePriceAnchor.commit()` is the only path to mint a root that verifies, so a bad root could validate fraudulent trades. The auto-defund trigger has a *narrower* dependency: it reads `latest().committedAt` only as a "is the oracle online" gate (§6.3, §6.10), not as a price source — drawdown observation samples `StrategyVault.navOf()` instead. A compromised oracle therefore can falsify proofs, but cannot directly suppress or fire a defund except by going silent (which trips `OracleStale` on the first observation, freezing rather than firing the trigger). v1 mitigations: (i) the oracle key is documented in §15.1 as a centralization point, (ii) `freshness(root)` enforces a 180s max-staleness window on every proof — stale oracle = proofs revert, (iii) `revokeRoot` / `unrevokeRoot` let the multi-sig kill (and unkill) specific committed roots without rotating the signer, (iv) every commit is a single signed event indexed by Goldsky so any manipulation is publicly observable in real time. v2 replaces the Helios oracle with a Pyth/Chainlink adapter with native staleness and circuit-breaker guarantees and adds a per-asset on-chain TWAP anchor that lets the defund path migrate from operator-NAV to oracle-priced marked NAV (§17 Phase 1).

**Threat: Strategy operator signs a flattering NAV during defund observation to suppress the trigger.**
Defense: **Partial in v1.** The Phase 4 caller-cadence defund path samples NAV from `StrategyVault.navOf()` — the same value the operator's `reportNAV` writes (§6.4). An operator who signs a NAV above threshold during a real drawdown can suppress observation, and the v1 NAV-divergence check (§6.4) does not catch this — it's a one-sided cash-floor check that catches under-reporting only, because there is no on-chain per-asset price source for an upper-bound recomputation. Mitigations available in v1: (a) reputation engine penalizes inconsistent NAV reports off-chain — a strategy with a divergent post-realization P&L vs reported NAV trajectory accrues reputation decay, which directly reduces allocator capital flow; (b) operators can't stop reporting indefinitely without freezing fee crystallization (HWM doesn't update) and accruing age-decay reputation hits; (c) when the strategy realizes (via fee settlement or unwind), the cash-on-hand reveals the gap and the same divergence check fires retroactively in the under-reporting direction. v2 closes the residual gap by reading `markedNAV` from a per-asset on-chain TWAP anchor (Algebra V3 pools on Kite mainnet, or a separate per-asset price-anchor service) so divergence is bidirectional — see §17 Phase 1.

**Threat: Strategy operator under-reports NAV to inflate drawdown and grief allocations.**
Defense: The §6.4 cash-floor NAV-divergence check fires when `signedNAV < baseAsset.balanceOf(strategyVault) × (1 - NAV_DIVERGENCE_THRESHOLD_BPS/10_000)` for two consecutive snapshots. The strategy class invariant `NAV ≥ cashHeld` (long-only spot) makes this an unambiguous lie. `NavDivergenceObserved` emits, multi-sig executes `slash` per §6.4. Cost to the operator: stake.

**Threat: User's Passport credentials are compromised.**
Defense: An attacker who steals the user's passkey + email recovers the AA wallet and can withdraw. This is the same threat model as any custodial-MPC product (Particle, Privy, Magic). Mitigation: Particle's email + passkey 2FA, plus the user can call `delegateToAllocator(address(0))` and `withdraw(maxCapital)` at any time. v2 considers an "external owner" flow that lets a power user point the AA wallet at a hardware-held EOA.

**Threat: Allocator's delegation key is compromised.**
Defense: The on-chain ACL bounds the attacker to the meta-strategy — they cannot exceed `maxCapital`, allocate to disallowed asset classes, or change the user's drawdown threshold. The user revokes by calling `delegateToAllocator(address(0))`.

**Threat: Smart contract bug.**
Defense: The Solidity surface is intentionally small (~2,830 LoC, per the §6.1 inventory). Audit-friendly. Pre-launch we run static analysis (Slither, Mythril) and aim for a community audit pass; Echidna property fuzz suites are scheduled alongside the Phase 1 external audit (see §16, §17).

**Threat: ZK circuit bug.**
Defense: Each circuit is small and reviewed. Unit tests cover edge cases (zero amounts, max amounts, boundary conditions). The trusted setup is a known limitation requiring future ceremony.

**Threat: Front-running of the allocator's rebalance transactions.**
Defense: Allocator transactions are gas-batched and use Kite's bundler. On Kite, MEV is naturally lower because the chain is AI-payments-focused, not DEX-heavy.

**Threat: Cross-chain message replay.**
Defense: LayerZero's standard nonce/replay protection. Plus per-strategy update sequence numbers in HeliosOApp.

### 15.3 What we explicitly don't claim

- **We don't claim the strategies will be profitable.** Markets are risky. Helios is infrastructure for capital allocation, not a return guarantee.
- **We don't claim the reputation system can't be gamed at all.** We claim it raises the cost of gaming above any rational gain, and we document the specific gaming vectors and their mitigations.
- **We don't claim full trustlessness in v1.** The reputation signer and the price oracle are centralization points. We say so plainly.
- **We don't claim production-readiness.** This is a hackathon submission with mainnet-portable contracts but a known list of items to address before institutional capital should touch it.

---

## 16. Out-of-scope for MVP

To be brutally clear about what we are *not* doing, so judges can score what's there fairly and so post-hackathon planning has a clear backlog.

- More than two reference allocators (Sentinel + Helix-lite; AllocatorSDK ships so others can build their own, but we don't seed >2 ourselves)
- Helix's regime-adaptive fee weighting and correlation-aware greedy allocation (the AllocatorSDK exposes the hooks — `pairwise_correlation_from_goldsky`, `btc_realized_vol_30d`, `detect_regime` — but Helix v1 ships fee-weighted greedy over reputation only; full §11.4.1 behaviour is post-hackathon Phase 1)
- Standalone Telegram bot (`@helios_market_bot`) — replaced in v1 by the dashboard activity rail, which consumes the same WS feed and applies the §13.2/`DESIGN.md §15` formatting rules (post-hackathon Phase 1)
- x402-paid prover/oracle/audit endpoints with Pieverse facilitator settlement (Choice G; the agent-economy demo polish is post-hackathon Phase 1)
- Bespoke d3 sunburst with mechanical step-animated rebalance (v1 ships a simpler concentric-ring viz; full bespoke treatment is v2 polish)
- `/docs` route with embedded operator + allocator guides (`/judge` links out to GitHub markdown instead)
- Echidna property tests (Slither + Mythril clean is the v1 contract security bar; Echidna fuzz suites are post-audit work, post-hackathon Phase 2)
- Permissionless strategy class registration (permissioned to the three classes for v1)
- Perpetuals / derivatives strategies (Kite has no native perp DEX; Hyperliquid integration deferred to roadmap — see Section 17)
- Inter-strategy correlation in allocator ranking (Sentinel doesn't do this; the SDK exposes hooks so allocators *can*)
- Capacity-adjusted Sharpe in reputation
- Production trusted setup (uses local PTAU)
- Decentralized reputation signer (single signer in v1)
- Chainlink/Pyth price oracle integration (uses Helios-operated oracle)
- Multiple stablecoins (USDC only)
- Slashing dispute mechanism (slash is owner-controlled in v1)
- Strategy class versioning and migration
- Insurance fund for stake-exhaustion edge cases
- Full mobile app (responsive web only in v1; Telegram bot and React Native are post-hackathon Phase 1/2)
- DAO governance (multi-sig in v1)
- Native token (no token in v1; fees are USDC)

---

## 17. Post-hackathon roadmap

Helios is designed as v1 of a real protocol, not a hackathon throwaway. The post-hackathon path:

### Phase 1 (Months 1-3 post-hackathon)

- Production trusted setup (Helios-specific ceremony or migration to existing setup)
- Migrate reputation signer to a 5-of-9 multi-sig
- **AllocatorSDK adoption push** — onboard 5-10 third-party allocators beyond Sentinel and the demo Helix, with documentation, partner outreach, and an "Allocator Grants" program seeded by protocol fees
- **Helix v2** — restore the regime-adaptive fee factor + correlation-aware greedy allocation deferred from v1 (`detect_regime` from BTC realized-vol percentiles, `pairwise_correlation_from_goldsky`, `helix_fee_factor` regime weighting per §11.4.1). Hooks already ship in the AllocatorSDK in v1 so any third-party allocator can adopt them earlier than Helix does.
- **`@helios_market_bot` Telegram bot** — consumes the existing dashboard WS feed; reuses `DESIGN.md §15` templates verbatim. Adds the user opt-in flow on `/dashboard` and a Telegram admin alerting channel for ops.
- **x402-paid services (Choice G)** — Pieverse facilitator integration; `services/prover`, `services/oracle`, `services/reputation` (audit endpoint) wrapped with x402-aware FastAPI middleware; Sentinel allocator-side x402 client; activity-rail `X402_SETTLED` badge.
- **Bespoke d3 sunburst** — replace the v1 concentric-ring viz with a hand-drawn d3 implementation including mechanical step animation on rebalance (~300ms ticked motion) and the mini-sunburst variant tightened up.
- **`/docs` route** — embed operator + allocator guides as MDX with version-pinned anchors instead of linking out to GitHub.
- Permissionless strategy class registration with circuit-submission gating
- Chainlink-backed price oracle adapter
- **Per-asset on-chain TWAP price anchor for defund marked NAV.** v1 ships caller-cadence persistence over `StrategyVault.navOf()` (§6.3) because the Phase 2 oracle commits Poseidon roots only — no per-asset on-chain reads. v2 adds an `OracleAssetPriceAnchor` (or reads Algebra V3 pool TWAPs on Kite mainnet directly) so the auto-defund path computes a fully on-chain-priced marked NAV and the §6.4 NAV-divergence slash deterrent stops being load-bearing for trigger correctness.
- **`StrategyRegistry.payDefundReward` (defund reward from strategy stake).** v1 routes the §6.3 defund reward from `AllocatorVault._accruedFees` instead, because the registry is immutable in Phase 3 and adding the helper requires a full registry redeploy + re-registration of every strategy. v2 rebuilds the registry (alongside the per-class governance + slashing-dispute work in §16) and restores the original "reward from strategy stake" routing.
- Independent smart contract audit (Trail of Bits or equivalent)

### Phase 2 (Months 4-6)

- Mainnet deployment on Kite L1
- USDT and USDG stablecoin support
- Capacity-adjusted Sharpe in reputation formula
- Slashing dispute mechanism (stake-weighted attestation)
- **Echidna property fuzz suites** — vault solvency, no allocation exceeds meta-strategy bounds, only drawdown-breached strategies can be permissionlessly defunded, reputation never overflows. Pairs with the Phase 1 external audit.
- Mobile app (React Native)
- Strategy class versioning and migration tooling
- **`basis_v1` strategy class — Hyperliquid integration.** Adds the perpetuals-funding-rate strategy class via Hyperliquid as the perp execution venue. The circuit proves: spot leg and perp leg are sized to be funding-neutral, perp leg is on an allowlisted Hyperliquid market, and trade direction matches a committed funding-rate signal exceeding threshold. This was deferred from v1 because Kite has no native perp DEX and Hyperliquid uses a non-EVM L1 with its own auth model — multi-week integration that wasn't compatible with the hackathon timeline. Adding it post-hackathon expands the marketplace into derivative-yield strategies.

### Phase 3 (Months 7-12)

- ZK-attested reputation computation (eliminates reputation signer entirely)
- Insurance fund seeded by protocol fees
- Cross-chain expansion: Optimism, Polygon, Avalanche, eventually Solana (via Wormhole/LayerZero)
- DAO governance launch
- Native token (only if there's a clear protocol-economic case)

The roadmap demonstrates that v1 is the foundation of a real product, not an aspiration.

---

## 18. Repository layout

```
helios/
├── README.md                       # The judge-friendly entry point
├── SPEC.md                         # This document
├── contracts/                      # Solidity (Foundry)
│   ├── src/
│   │   ├── UserVault.sol
│   │   ├── AllocatorVault.sol
│   │   ├── StrategyVault.sol
│   │   ├── StrategyRegistry.sol
│   │   ├── AllocatorRegistry.sol   # Allocator manifests + reputation anchor
│   │   ├── ReputationAnchor.sol
│   │   ├── HeliosOApp.sol
│   │   ├── verifiers/
│   │   │   ├── MomentumV1Verifier.sol
│   │   │   ├── MeanReversionV1Verifier.sol
│   │   │   └── YieldRotationV1Verifier.sol
│   │   └── interfaces/
│   ├── test/                       # Foundry tests (target: 90%+ coverage)
│   ├── script/                     # Deployment scripts (per chain)
│   └── deployments/
│       ├── kite-testnet.json
│       ├── base-sepolia.json
│       └── arbitrum-sepolia.json
├── circuits/
│   ├── momentum_v1.circom
│   ├── mean_reversion_v1.circom
│   ├── yield_rotation_v1.circom
│   └── build/                      # .wasm, .zkey, verification_key.json
├── packages/
│   ├── strategy-sdk/               # Python SDK for strategy operators
│   ├── allocator-sdk/              # Python SDK for allocator operators (v1 deliverable)
│   └── helios-cli/                 # CLI for deployment, backtest, etc.
├── services/
│   ├── sentinel/                   # Helios Sentinel — reference allocator
│   ├── helix/                      # Helios Helix — secondary demo allocator (built on AllocatorSDK)
│   ├── reputation/                 # The Reputation Engine
│   ├── prover/                     # The Prover Service (Node + snarkjs)
│   ├── oracle/                     # The reference price + yield oracle
│   └── bot/                        # Telegram bot (deferred to post-hackathon Phase 1 — see §16/§17)
├── frontend/                       # Next.js 14 web app
│   └── src/
│       ├── app/
│       │   ├── page.tsx
│       │   ├── strategies/
│       │   ├── allocators/         # Allocator marketplace (Sentinel, Helix, third-party)
│       │   ├── dashboard/
│       │   ├── audit/
│       │   └── judge/              # The judge eval page
│       ├── components/
│       └── lib/
├── reference-strategies/           # The three reference strategy implementations
│   ├── momentum_v1/
│   ├── mean_reversion_v1/
│   └── yield_rotation_v1/
├── subgraph/                       # Goldsky subgraph definition
│   ├── subgraph.yaml
│   ├── schema.graphql
│   └── src/
├── deploy/                         # VPS deployment scripts (PM2, Nginx, Docker)
├── docs/                           # Long-form documentation
│   ├── operator-guide.md
│   ├── allocator-guide.md          # How to build a competing allocator using AllocatorSDK
│   ├── reputation-math.md
│   ├── circuit-specs.md
│   ├── threat-model.md
│   └── audit-checklist.md
└── docker-compose.yml              # Single-command full-stack local boot
```

---

## 19. Judge quick-evaluation guide

> *Time required: 5 minutes.*

For judges of the Kite AI Global Hackathon 2026 evaluating Helios.

### Step 1: Watch the 90-second video
Link: [helios.market/demo-video](#)

### Step 2: Open the live app
Link: [helios.market](#) → switch to Kite testnet

### Step 3: Try the demo flow
Click "Run Demo Scenario" on the dashboard. Watch the 3-minute scripted scenario play out: cascade allocation → drawdown → auto-defund → cross-chain reputation update.

### Step 4: Verify on-chain
- Strategy Registry: [Kitescan link](#)
- A sample TradeAttested event: [Kitescan link](#)
- A sample auto-defund tx: [Kitescan link](#)
- The cross-chain reputation message: [LayerZero scan link](#)

### Step 5: Re-verify a ZK proof yourself
```
git clone https://github.com/helios-market/helios
cd helios
npm install
node scripts/verify-trade.js <txhash>
```
This re-runs the Groth16 verification off-chain and confirms it matches the on-chain result.

### Step 6: Read the moats
Three sections worth your time, in order:
- Section 9 — the ZK strategy attestation (the technical moat)
- Section 8 — the reputation engine (the IP moat)
- Section 15 — the threat model (the credibility moat)

### Step 7: Score
Helios's bid for the Trading track rests on:
- Direct hit on the "agent-first, end-to-end autonomous" thesis
- All three Kite uniquely-uncopiable primitives used as load-bearing
- ZK-attested execution as a genuine technical novelty no other submission will likely have
- A reputation system designed for capital-allocation defensibility
- Cross-chain reputation as a meaningful (not decorative) LayerZero use
- A real product roadmap that goes beyond the hackathon

---

*Built for the Kite AI Global Hackathon 2026 — Agentic Trading & Portfolio Management track. Submitted by Team Helios.*
