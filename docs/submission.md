# Helios — Submission Explanation

**What it is**

Helios is a programmatic capital market for AI trading agents on the Kite chain. A user signs **one** meta-strategy through Kite Passport (e.g. *"up to $10,000 across momentum strategies trading BTC/ETH/SOL, max 30% per strategy, defund on 15% drawdown"*). From that single approval an autonomous **Allocator Agent** routes capital across competing **Strategy Agents**; every trade carries a Groth16 ZK proof binding it to the strategy's declared class; reputation accrues from realized, attested performance and flows across chains via LayerZero V2. Built for the **Kite AI Hackathon 2026 — Agentic Trading & Portfolio Management** track.

**The problem**

Deploying capital with an AI trading agent today means either running one yourself (hard, risky) or trusting a centralized AI fund (no verifiable performance, no recourse). There is no market that forces agents to compete on performance, lets capital flow programmatically to good ones, cryptographically constrains what an agent can do, and makes reputation portable across chains. Helios is that mechanism.

**The agentic design**

Two fully autonomous on-chain roles. The **Allocator agent** (Sentinel) scores live strategies on `f(reputation, stake, capacity, freshness)` every 60s and delegates strictly inside the user's signed envelope. **Strategy agents** are trader agents with class-bound autonomy: rules, RL, or an LLM all work, because the ZK class binding — not the code — defines an agent's type. A reference strategy has Claude decide every trade while the chain enforces the bounds.

**What I built**

A full-stack monorepo (~524 commits, 6 phases): ~7,300 LOC Solidity (403 tests, 90% coverage), 3 Circom/Groth16 circuits, allocator + reputation + oracle + prover services, three public PyPI SDKs, a Next.js frontend, and Goldsky subgraphs — deployed end-to-end across three chains.

**Key achievements (proven on-chain)**

- 8 autonomous ZK-attested trades fired from the Kite mean-reversion vault, each independently re-verifiable in one command.
- 6 live strategy vaults across Kite, Base, and Arbitrum testnets.
- Real cross-chain reputation via LayerZero V2 (Base→Kite, 0→750 in one hop).
- LLM-driven strategy reusing the existing verifier with zero protocol change.
- Reproducible by judges in five minutes, no VPS required.

**Honest limitations**

Cross-chain capital bridging was built and proven, then deliberately deactivated — LayerZero's fixed fee floor makes per-rebalance bridging impractical, so v1 keeps capital chain-local. Centralized v1 trust surfaces (reputation signer, oracle) are documented with a multi-sig → ZK-attested migration path.
