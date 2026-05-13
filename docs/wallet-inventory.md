# Wallet inventory

Snapshot of every wallet currently signing Helios txs in production, grouped by chain. Updated 2026-05-13 after the signer-rotation pass.

Source of truth: addresses derived from `/srv/helios/.env` on the Helios VPS via `eth_account.Account.from_key(...)` inside the oracle container; on-chain roles cross-referenced against `contracts/deployments/*.json` + live contract calls.

See [`project_deployer_pk_signer_collapse`](../../.claude/projects/-home-emark-helios/memory/project_deployer_pk_signer_collapse.md) memory entry for the history behind the per-chain deployer-EOA collapses and rotation plan.

---

## Shared across all chains — deployer EOA

| Wallet | Env vars (collapsed) | Role |
|---|---|---|
| `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25` | `DEPLOYER_PK`, `SENTINEL_OPERATOR_PK`, `OPERATOR_PK`, `NAV_ORACLE_PK`, `YIELD_ROT_OPERATOR_PK` | Proxy admin / mint authority on Kite + Base + Arb; Sentinel allocator caller; yr.kite operator + navOracle; yr.arb operator + navOracle placeholder |

This is a 5-way collapse — Sentinel, yr.kite, and yr.arb still sign as deployer (low-frequency enough that they didn't surface in the original ~12 tx/min nonce-drift profile that triggered the partial rotation).

---

## Kite testnet (chain 2368)

| Wallet | Service | On-chain role |
|---|---|---|
| `0xc419ECda32dAA81AC50e46BcCb711022C2ee0693` | services/reputation | `reputationAnchorV2Bis.reputationSigner()` |
| `0x32b0112C085c25fea23C92D8f0540D26389006A7` | services/oracle | `oraclePriceAnchor.oracleSigner()` + `oracleYieldAnchor.oracleSigner()` |
| `0xED71e8eE58b3A68095de911d491b237555932782` | services/oracle (`RouterPriceMirror` keeper) | `MockSwapRouter.owner()` |
| `0x68c6Bcc256Cd0eb5D60879edC30c5551B8F91B8B` | reference-strategies/momentum_v1 | `phase6VaultMomentum` operator + navOracle |
| `0xeC644f029E1a8b4d709d83e5F9487B5a04b167E5` | reference-strategies/mean_reversion_v1 | `phase6VaultMeanReversion` operator + navOracle |
| `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25` (deployer) | reference-strategies/yield_rotation_v1, services/sentinel | yr.kite operator + navOracle; AllocatorVault caller for `allocate`/`rebalance`/`defund` |

Per-class strategy services use the same EOA for both `OPERATOR_PK` and `NAV_ORACLE_PK` — intentional (per `project_phase6_ws9_dedicated_keys.md`); collapses ops + nav-signing onto one dedicated EOA per class to break shared-deployer nonce contention.

Phase-6 vault variants 2 + 3 of each class have their own operator + navOracle EOAs too, but those services are not currently running on the VPS; addresses can be queried via `cast call <vault> "manifest()"`.

---

## Base Sepolia (chain 84532)

| Wallet | Service | On-chain role |
|---|---|---|
| `0x32b0112C085c25fea23C92D8f0540D26389006A7` | services/oracle (price mirror) | Base `oraclePriceAnchor.oracleSigner()` — same key as Kite. ⚠️ Gas-starved; needs ~0.05 ETH faucet top-up at [Alchemy Base Sepolia faucet](https://www.alchemy.com/faucets/base-sepolia) for sustained mirror operation |
| `0xf95Ba60e81bf483cFdc95Cfe52CCf3029ef09e03` | reference-strategies/momentum_v1 (Base) | `phase6VaultMomentumBase` operator + navOracle |
| `0xA21Aaf25544cD43505B6e11512E1268Dbd453476` | reference-strategies/mean_reversion_v1 (Base) | `phase6VaultMeanReversionBase` operator + navOracle |

---

## Arbitrum Sepolia (chain 421614)

| Wallet | Service | On-chain role |
|---|---|---|
| `0x32b0112C085c25fea23C92D8f0540D26389006A7` | services/oracle (price + yield mirror) | Arb `oraclePriceAnchor.oracleSigner()` + `oracleYieldAnchor.oracleSigner()` — same key as Kite + Base. Funded ~0.02 ETH; healthy. |
| `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25` (deployer) | reference-strategies/yield_rotation_v1 (Arb) | `phase6VaultYieldRotationArb` operator + navOracle — placeholder until a dedicated yr.arb EOA is generated (see remaining-rotation notes) |

---

## Rotation status

✅ **Rotated 2026-05-13** (Kite anchors + remote oracle mirrors):
- `REPUTATION_SIGNER_PK` → `0xc419ECda…`
- `ORACLE_SIGNER_PK` → `0x32b0112C…` (reused on Base + Arb mirrors)
- `ROUTER_MIRROR_SIGNER_PK` → `0xED71e8eE…`

⏳ **Gated on CXR-0b impl upgrade — setter code ready, deploy pending:**

AllocatorVault + StrategyVault have no `setOperator` / `setNavOracle` in the live impls. Setters now exist at HEAD (3 + 6 tests green) and will ship via the pending CXR-0b impl deploys.

After CXR-0b lands:
- `SENTINEL_OPERATOR_PK` (Sentinel allocator caller) — rotate via `AllocatorVault.setOperator`
- `YIELD_ROT_OPERATOR_PK` + new `YIELD_ROT_NAV_ORACLE_PK` (yr.kite + yr.arb) — rotate via `StrategyVault.setOperator` + `setNavOracle` on `phase6VaultYieldRotation` + `phase6VaultYieldRotationArb`
- yr.kite Variant 2/3 vaults — rotate same way if you want operator parity (services not running)
- Bare `OPERATOR_PK` / `NAV_ORACLE_PK` env vars — delete after step above, plus add a `NAV_ORACLE_PK: ${YIELD_ROT_NAV_ORACLE_PK}` compose override for yr.kite + yr.arb to match the mom/mr pattern

Full runbook (7 steps including funding amounts, exact cast commands, verification) lives in `memory/project_deployer_pk_signer_collapse.md`.

⚠️ **Operational gas state:**
- Kite: deployer balance ~0.30 KITE, drains ~0.00006 KITE/min, ~85h to drain. Not urgent.
- Base oracle signer (`0x32b0112C…`): gas-starved, ~0.0006 ETH; needs faucet top-up.
- Arb oracle signer (`0x32b0112C…`): funded 0.02 ETH; healthy.
