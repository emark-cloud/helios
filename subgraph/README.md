# @helios/subgraph

Goldsky subgraph indexing Helios events across Kite, Base, and Arbitrum.

## Phase status

- **Phase 0** — schema frozen. No datasources wired.
- **Phase 1** — Kite testnet datasources (`StrategyRegistry`, `AllocatorRegistry`, `AllocatorVault`, `ReputationAnchor`) + handlers land alongside the deployed contracts.
- **Phase 5** — Base Sepolia + Arbitrum Sepolia datasources added; cross-chain `ReputationMessageReceived` events joined into canonical `ReputationSnapshot`.

## Workflows

```bash
pnpm --filter @helios/subgraph codegen       # regenerate AssemblyScript types from schema
pnpm --filter @helios/subgraph build         # compile WASM
pnpm --filter @helios/subgraph deploy        # ships to Goldsky (requires GOLDSKY_API_KEY)
```

## Conventions

- ABIs come from `../packages/contracts-abi/src/abis/` — don't duplicate them here.
- Mapping files (`src/*.ts`) handle at most one datasource each. Keep them small.
- Every subgraph entity corresponds 1:1 with a concept in `Helios.md §4`.
