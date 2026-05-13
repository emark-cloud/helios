# Wallet inventory

Snapshot of every wallet currently signing Helios txs in production, grouped by chain. Updated 2026-05-13 after the signer-rotation pass.

Source of truth: addresses derived from `/srv/helios/.env` on the Helios VPS via `eth_account.Account.from_key(...)` inside the oracle container; on-chain roles cross-referenced against `contracts/deployments/*.json` + live contract calls.

See [`project_deployer_pk_signer_collapse`](../../.claude/projects/-home-emark-helios/memory/project_deployer_pk_signer_collapse.md) memory entry for the history behind the per-chain deployer-EOA collapses and rotation plan.

---

## Shared across all chains — deployer EOA

| Wallet | Env vars (collapsed) | Role |
|---|---|---|
| `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25` | `DEPLOYER_PK`, `NAV_ORACLE_PK` (bare) | Proxy admin / mint authority on Kite + Base + Arb; yr.arb operator + navOracle (rotation deferred — Arb impl needs CXR upgrade per task #96) |

Post-2026-05-13 rotation: SENTINEL_OPERATOR_PK + YIELD_ROT_OPERATOR_PK now point at dedicated EOAs (see Kite table below). Only yr.arb still signs as deployer until its Arb-side impl is upgraded to one carrying `setOperator`/`setNavOracle`.

---

## Kite testnet (chain 2368)

| Wallet | Service | On-chain role |
|---|---|---|
| `0xc419ECda32dAA81AC50e46BcCb711022C2ee0693` | services/reputation | `reputationAnchorV2Bis.reputationSigner()` |
| `0x32b0112C085c25fea23C92D8f0540D26389006A7` | services/oracle | `oraclePriceAnchor.oracleSigner()` + `oracleYieldAnchor.oracleSigner()` |
| `0xED71e8eE58b3A68095de911d491b237555932782` | services/oracle (`RouterPriceMirror` keeper) | `MockSwapRouter.owner()` |
| `0x68c6Bcc256Cd0eb5D60879edC30c5551B8F91B8B` | reference-strategies/momentum_v1 | `phase6VaultMomentum` operator + navOracle |
| `0xeC644f029E1a8b4d709d83e5F9487B5a04b167E5` | reference-strategies/mean_reversion_v1 | `phase6VaultMeanReversion` operator + navOracle |
| `0x0A7d03433CD89827Feb935A80C37c46D58f7dF92` | services/sentinel | `AllocatorVault.operator()` caller for `allocate`/`rebalance`/`defund` (rotated 2026-05-13 from deployer) |
| `0x86918Bf3cC030688F0d88f9c967646537D506041` | reference-strategies/yield_rotation_v1 | `phase6VaultYieldRotation` operator + navOracle (rotated 2026-05-13 from deployer) |

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
| `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25` (deployer) | reference-strategies/yield_rotation_v1 (Arb) | `phase6VaultYieldRotationArb` operator + navOracle — rotation gated on Arb-side impl upgrade (task #96). EOA-B `0x86918Bf3…` already provisioned + funded with 0.05 ETH-Arb, awaiting impl. |

---

## Rotation status

✅ **Rotated 2026-05-13** (Kite anchors + remote oracle mirrors):
- `REPUTATION_SIGNER_PK` → `0xc419ECda…`
- `ORACLE_SIGNER_PK` → `0x32b0112C…` (reused on Base + Arb mirrors)
- `ROUTER_MIRROR_SIGNER_PK` → `0xED71e8eE…`

✅ **Rotated 2026-05-13 (afternoon, post CXR-0b impl upgrade)** — AllocatorVault + StrategyVault setters live:
- `SENTINEL_OPERATOR_PK` → `0x0A7d03433CD89827Feb935A80C37c46D58f7dF92` (AllocatorVault.operator on Kite)
- `YIELD_ROT_OPERATOR_PK` + new `YIELD_ROT_NAV_ORACLE_PK` → `0x86918Bf3cC030688F0d88f9c967646537D506041` (yr.kite operator + navOracle)
- `deploy/docker-compose.prod.yml` yr.kite block patched with `OPERATOR_PK: ${YIELD_ROT_OPERATOR_PK}` + `NAV_ORACLE_PK: ${YIELD_ROT_NAV_ORACLE_PK}` overrides (matches mom/mr pattern)

⏳ **Still pending — yr.arb rotation gated on Arb-side impl upgrade:**

`phase6VaultYieldRotationArb`'s current Arb impl `0x9c3eb82e3b17d64ac3957741857962b51a0200e2` lacks `setOperator`/`setNavOracle` (it has `setRegistry` only — WS11 setter set, not CXR-aware). Deploy a fresh CXR-aware `StrategyVault` impl on Arb-Sepolia (constructor args: Arb `oraclePriceAnchor` + `oracleYieldAnchor`), `upgradeToAndCall` yr.arb to it, then `setOperator(0x86918Bf3…)` + `setNavOracle(0x86918Bf3…)`. Task #96.

- yr.kite Variant 2/3 vaults — operator still = deployer on-chain (services not running); rotate same way if you want operator parity.
- Bare `OPERATOR_PK` / `NAV_ORACLE_PK` env vars — yr.arb still reads bare `NAV_ORACLE_PK` from .env, so delete only after task #96 closes.

Full runbook (funding amounts, exact cast commands, verification) lives in `memory/project_deployer_pk_signer_collapse.md`.

⚠️ **Operational gas state:**
- Kite: deployer balance ~0.30 KITE, drains ~0.00006 KITE/min, ~85h to drain. Not urgent.
- Base oracle signer (`0x32b0112C…`): gas-starved, ~0.0006 ETH; needs faucet top-up.
- Arb oracle signer (`0x32b0112C…`): funded 0.02 ETH; healthy.
