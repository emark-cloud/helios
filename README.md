# Helios

**A programmatic capital market for AI trading agents on Kite.**

Users sign one meta-strategy. An allocator agent autonomously routes their capital across competing strategy agents. Every trade carries a Groth16 ZK proof binding it to the strategy's declared class. Reputation accrues from realized, attested performance and flows across chains via LayerZero.

Built for the Kite AI Global Hackathon 2026 — Agentic Trading & Portfolio Management track.

## Judges — start here

- **Live demo + 5-step eval checklist** → [`/judge`](https://helios.market/judge) on the deployed frontend
- **Demo video (3 min)** → see `/judge` (link populated 48 h before submission)
- **Independent ZK re-verification** → [`scripts/verify-trade.js`](./scripts/verify-trade.js)
- **Self-sufficient artifacts** (no VPS required): RPC URL, all deployed addresses, Goldsky endpoint, Kitescan deeplinks all surface on `/judge` directly from `contracts/deployments/kite-testnet.json`.

### Reproduce the demo in 5 minutes

```bash
# 1. Clone + install
git clone https://github.com/emark-cloud/helios.git && cd helios
pnpm install && uv sync && forge install --root contracts

# 2. Boot the local stack (Postgres, prover, services, frontend)
pnpm dev

# 3. Run the cascade scenario end-to-end against the local stack
scripts/e2e-scenario.sh

# 4. Independently verify any attested trade against Kite testnet
npm i ethers@^6
node scripts/verify-trade.js <tx-hash>   # exit 0 = PASS, 1 = FAIL
```

Step 3 produces a real `executeWithProof` on the local stack and prints
the resulting tx hash; step 4 re-verifies that proof against the
on-chain class verifier. Cold-start runtime target: ≤ 10 minutes.

## Repo map

| Path | Purpose |
|---|---|
| [`contracts/`](./contracts) | Foundry project (Solidity, tests, deploy scripts, deployments JSON) |
| [`circuits/`](./circuits) | Circom circuits + snarkjs build output |
| [`packages/strategy-sdk/`](./packages/strategy-sdk) | `helios-strategy-sdk` PyPI package |
| [`packages/allocator-sdk/`](./packages/allocator-sdk) | `helios-allocator-sdk` PyPI package |
| [`packages/helios-cli/`](./packages/helios-cli) | `helios-trader-cli` PyPI CLI |
| [`packages/contracts-abi/`](./packages/contracts-abi) | ABI freeze module — single source of truth for ABI bindings |
| [`services/sentinel/`](./services/sentinel) | Reference allocator (FastAPI) |
| [`services/helix/`](./services/helix) | Second reference allocator — correlation-aware |
| [`services/reputation/`](./services/reputation) | Reputation engine (reads Goldsky → signs scores → posts on-chain) |
| [`services/prover/`](./services/prover) | Groth16 proof-generation HTTP wrapper around snarkjs |
| [`services/oracle/`](./services/oracle) | Helios-operated price + yield oracle |
| [`reference-strategies/`](./reference-strategies) | The three reference strategy implementations |
| [`subgraph/`](./subgraph) | Goldsky subgraph manifest, schema, and mappings |
| [`frontend/`](./frontend) | Next.js 14 App Router frontend |
| [`deploy/`](./deploy) | VPS deploy: PM2, Nginx, Dockerfiles per service |
| [`scripts/`](./scripts) | E2E scenarios, verify-trade.js, preflight + measurement scripts |
| [`docs/`](./docs) | Long-form docs (operator-guide, allocator-guide, threat-model, audit-checklist, …) |

## Documentation

- **Product spec** → [`Helios.md`](./Helios.md)
- **Operational guide for sessions** → [`CLAUDE.md`](./CLAUDE.md)
- **Phase 6 acceptance** → [`docs/phase6-acceptance.md`](./docs/phase6-acceptance.md)
- **Operator guide** (ship a strategy) → [`docs/operator-guide.md`](./docs/operator-guide.md)
- **Allocator guide** (ship a competing allocator) → [`docs/allocator-guide.md`](./docs/allocator-guide.md)
- **Reputation math** → [`docs/reputation-math.md`](./docs/reputation-math.md)
- **Circuit specs** → [`docs/circuit-specs.md`](./docs/circuit-specs.md)
- **Threat model** → [`docs/threat-model.md`](./docs/threat-model.md)
- **Audit checklist** (Slither / Mythril triage) → [`docs/audit-checklist.md`](./docs/audit-checklist.md)
- **Backtest reports** → [`docs/backtests/`](./docs/backtests)

## Rate limits & scoped permissions

Helios enforces several layers of scoping so a runaway agent cannot exceed user-set bounds. Concrete values (full detail in [`deploy/README.md`](./deploy/README.md)):

| Surface | Bound | Where it's enforced |
|---|---|---|
| Per-strategy capital cap | User-set bps of total deposit | Solidity ACL in `contracts/src/UserVault.sol` (`maxAllocPerStrategyBps`) |
| Read endpoints (`GET`/`HEAD`/`OPTIONS`) | 100 req/min per IP | Nginx zone `helios_read` in `deploy/nginx/helios.conf` |
| Write endpoints (`POST`/`PUT`/`PATCH`/`DELETE`) | 10 req/min per IP | Nginx zone `helios_write` |
| Prover (`/prove`) | 5 req/min per IP | Nginx zone `helios_prover` (Groth16 generation is 5–15 s/proof) |
| Strategy outbound trade frequency | `min_bar_interval` (default 60 s) | `helios-strategy-sdk` self-throttle |
| Allocator decision frequency | `SENTINEL_DECISION_INTERVAL` env | Application-side in `services/sentinel/` |
| Signer keys (oracle, reputation, deployer) | Single-purpose, on-chain registered | `OracleAnchor.signers`, `ReputationAnchor.signers`, `AllocatorRegistry.setSigner` |
| Cross-contract calls | Tightest available modifier | `onlyOwner`, `onlyAllocator`, `onlyReputationAnchor`, `onlyOApp` |

Trip a Nginx rate limit and the response is **HTTP 429** (set explicitly via `limit_req_status`); SDK clients should treat this as the back-off signal.

## Quick start (developers)

Prerequisites: Node 20+, pnpm 9+, Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Foundry (`curl -L https://foundry.paradigm.xyz | bash`), Circom 2.1.9+, Docker.

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

Copy `.env.example` → `.env` and fill in at least `KITE_RPC_URL`, `DATABASE_URL`, `KITE_PASSPORT_SESSION_ID`. See [`CLAUDE.md`](./CLAUDE.md) for the full env-var inventory and per-track conventions.

## Status

Phase 6 — polish + submission. Phases 0–5 complete (`v0.5.0` shipped Phase 5 cross-chain on 2026-05-08); Phase-6 real-price cutover landed 2026-05-09 (`v0.6.0-realprice` at `0034fb4`); Phase-6 acceptance + multi-chain bring-up tagged `v0.6.0` on 2026-05-14. Nine multi-asset StrategyVaults active on Kite testnet against live BTC/ETH/SOL prices, plus three §12.1 cross-chain vaults live on Base + Arb Sepolia. See [`docs/phase6-acceptance.md`](./docs/phase6-acceptance.md) for the multi-chain evidence and [`docs/active-strategies.md`](./docs/active-strategies.md) for the per-vault breakdown.

## License

MIT. See [`LICENSE`](./LICENSE).
