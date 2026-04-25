# Helios

**A programmatic capital market for AI trading agents on Kite.**

Users sign one meta-strategy. An allocator agent autonomously routes their capital across competing strategy agents. Every trade carries a Groth16 ZK proof binding it to the strategy's declared class. Reputation accrues from realized, attested performance and flows across chains via LayerZero.

Built for the Kite AI Global Hackathon 2026 — Agentic Trading & Portfolio Management track.

## Start here

- **Product spec** → [`Helios.md`](./Helios.md)
- **Design brief** → [`DESIGN.md`](./DESIGN.md)
- **Operational guide** → [`CLAUDE.md`](./CLAUDE.md)
- **Phase checklist** → [`TODO.md`](./TODO.md)

## Quick start

Prerequisites: Node 20+, pnpm 9+, Python 3.11+, `uv`, Foundry, Circom 2.1.9+, Docker.

```bash
pnpm install
uv sync
forge install --root contracts

# Boot the local stack (Postgres, anvil forks, services, frontend)
pnpm dev

# Per-surface
pnpm contracts:test          # Foundry tests
pnpm circuits:test           # Circuit unit tests
pnpm --filter frontend dev   # Frontend at :3000
```

Copy `.env.example` → `.env` and fill in at least `KITE_RPC_URL`, `DEPLOYER_PK`, `DATABASE_URL`.

## Status

Phase 0 — bootstrap. See [`TODO.md`](./TODO.md) for the live checklist.

## License

MIT. See [`LICENSE`](./LICENSE).
