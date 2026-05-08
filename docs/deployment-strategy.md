# Deployment strategy — hybrid testnet → mainnet

> **Status: Stretch (optional). Mainnet promotion is not in v1 scope** as of 2026-05-08. v1 ships and demos on Kite Testnet through Phase 6 (polish + submission). This document is the playbook **if** we elect to promote to Kite mainnet (chain 2366) after Phase 6 acceptance. Kept intact so the path is reversible — nothing in v1 depends on it.

Decided 2026-04-25. Updated 2026-04-27 (Phase 1 testnet live). Reframed 2026-05-08 (mainnet dropped from planned scope; now stretch).
Read before any deployment-related work.

## TL;DR

- **Phases 1–4**: Kite testnet only. Fast iteration, no real money, mock DEX is fine.
- **Phase 5**: cross-chain testnets (Base Sepolia, Arbitrum Sepolia) per existing plan.
- **Phase 6**: promote a polished copy to **Kite mainnet** for the judge demo. Real Algebra trades, real tokens, small demo capital.
- Testnet deployment stays alive throughout as the dev/staging environment.

## Why hybrid

Pure testnet: fast iteration, free, but mock DEX is an obvious tell to judges and we never exercise the real Algebra/LayerZero surfaces.

Pure mainnet: credible demo, real DEX/oracle/bridges available — but every redeploy costs real KITE, bugs in vault contracts risk real funds, slower iteration loop, and Passport (which is currently pre-public-launch on testnet) may not be available on mainnet at submission time.

Hybrid lets us iterate cheaply for the long tail of development and ship a credible demo at submission, with the upgrade-to-mainnet step being a documented one-shot rather than a continuous cost.

## What this means per workstream

### Phase 1 (current — backend live, frontend open)

- ✅ All contracts deployed to Kite testnet (Track B sign-off 2026-04-27, chainId 2368, deployer `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25`). `contracts/deployments/kite-testnet.json` is the only addresses file and it's populated with real addresses; broadcast log under `contracts/broadcast/DeployPhase1.s.sol/2368/run-latest.json`.
- ✅ `MockSwapRouter` + `MockPool` live on testnet so trades have something to settle against. (Real Algebra still not documented on Kite testnet — memory `reference_kite_contract_surface`.)
- ✅ Oracle service uses off-chain price source (Binance → Coingecko fallback) — no on-chain Algebra TWAP available on testnet.
- Phase 1 keccak256 oracle chain is Solidity-native; Phase 2 swaps to Poseidon so the momentum circuit can consume the on-chain root directly.

### Phases 2–4

- Same as Phase 1: testnet only.
- New strategy classes (mean reversion, yield rotation), Helix allocator, frontend completion — all testnet.
- Subgraph indexes only the testnet datasources.

### Phase 5 (cross-chain)

- Base Sepolia + Arbitrum Sepolia per existing plan.
- LayerZero V2 wired across all three testnets.
- **Decision point at end of Phase 5**: confirm hackathon rules + Passport availability before committing to mainnet promotion. If either blocks, fall back to testnet-only demo.

### Phase 6 (audit + demo)

Adds a **mainnet promotion track**:

- Slither / Mythril / Echidna run **clean** on every Phase 1 contract before any mainnet deploy. No "we'll fix it after the demo."
- `contracts/script/DeployMainnet.s.sol` deploys the same contracts to Kite mainnet.
- Real Algebra Integral router/factory/positions get wired in (replacing `MockSwapRouter`).
- Oracle service swaps `oracle/sources/binance.py` for `oracle/sources/algebra.py` (TWAP from real pools).
- LayerZero V2 + Lucid bridge contracts on Kite mainnet replace testnet stubs.
- Demo capital: **$100–500 max**, sourced from a dedicated demo wallet, never from user funds.
- `contracts/deployments/kite-mainnet.json` is created here, frontend gets a chain switcher.
- Subgraph adds mainnet datasources (a separate Goldsky subgraph version).

## Open verifications (need answers before Phase 5 → 6 transition)

1. **Hackathon rules** — does @Kite AI Global Buildathon allow / require / forbid mainnet submissions? Ask Kite team in Discord.
2. **Passport on mainnet** — when Passport launches publicly, will it be on mainnet, testnet, or both? Need both for the hybrid demo to work.
3. **KITE acquisition** — confirm we can buy KITE on an exchange (currently trades as ERC-20 on Ethereum at `0x904567252D8F48555b7447c67dCA23F0372E16be`) and bridge to Kite mainnet via Lucid. Estimate gas budget for full Phase 1 contract deploy + first month of activity.
4. **Goldsky mainnet pricing** — confirm Goldsky free tier covers a second mainnet subgraph deployment, or budget the upgrade.

## Failure mode

If at Phase 5 → 6 transition any of the above blocks mainnet promotion:

- Submit testnet demo with mainnet-readiness clearly documented.
- `MockSwapRouter` becomes the documented "Phase 1 expedient pending mainnet rollout."
- `/judge` page links to the mainnet promotion plan (this doc) so judges see the full intent.

The hybrid plan is designed so that "stay on testnet" is always a safe fallback — every architectural decision through Phase 5 is testnet-compatible.

## Reference: Kite mainnet contracts (per docs.gokite.ai)

| Contract | Address |
|---|---|
| AlgebraFactory | `0x10253594A832f967994b44f33411940533302ACb` |
| SwapRouter | `0x03f8B4b140249Dc7B2503C928E7258CCe1d91F1A` |
| NonfungiblePositionManager | `0xD637cbc214Bc3dD354aBb309f4fE717ffdD0B28C` |
| WKITE | `0xcc788DC0486CD2BaacFf287eea1902cc09FbA570` |
| USDC.e | `0x7aB6f3ed87C42eF0aDb67Ed95090f8bF5240149e` |
| WETH | `0x3D66d6c3201190952e8EA973F59c4428b32D5F9b` |

Plus LayerZero V2 endpoint and Lucid bridge — addresses to be added when Phase 5 starts.
