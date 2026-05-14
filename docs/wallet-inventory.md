# Wallet inventory

Snapshot of every wallet currently signing Helios txs in production, grouped by chain. Updated 2026-05-14 after yr.arb rotation closed (task #96).

Source of truth: addresses derived from `/srv/helios/.env` on the Helios VPS via `eth_account.Account.from_key(...)` inside the oracle container; on-chain roles cross-referenced against `contracts/deployments/*.json` + live contract calls.

See [`project_deployer_pk_signer_collapse`](../../.claude/projects/-home-emark-helios/memory/project_deployer_pk_signer_collapse.md) memory entry for the history behind the per-chain deployer-EOA collapses and rotation plan.

---

## Shared across all chains — deployer EOA

| Wallet | Env vars (collapsed) | Role |
|---|---|---|
| `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25` | `DEPLOYER_PK` | Proxy admin / mint authority on Kite + Base + Arb. All strategy operator/navOracle roles now rotated off this EOA. |

Post-2026-05-13/14 rotation: SENTINEL_OPERATOR_PK + YIELD_ROT_OPERATOR_PK (yr.kite AND yr.arb) now point at dedicated EOAs (see per-chain tables below).

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
| `0x86918Bf3cC030688F0d88f9c967646537D506041` | reference-strategies/yield_rotation_v1 (Arb) | `phase6VaultYieldRotationArb` operator + navOracle (rotated 2026-05-14 after Arb-side impl upgrade to `0x4e6928a2…`; shares the same EOA as yr.kite). |

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

✅ **Rotated 2026-05-14 (yr.arb closure — task #96):**
- yr.arb's Arb-side StrategyVault impl upgraded to `0x4e6928a2Ac4c9E9dE99d4F33Fa18d31EA0bFA45c` (UUPS broadcast via `UpgradeRemoteVaultsToCXR.s.sol`). The new impl carries `setOperator`/`setNavOracle` setters.
- `setOperator(0x86918Bf3…)` tx `0x7748afa3aaecb4cf1d0b9f76b1012e8a0e3c9f772cc2cdb0af1148a6b67e9f85`
- `setNavOracle(0x86918Bf3…)` tx `0x57028f73fc367cd8a57315969a19d6c897e260c9071b2934f3c3e1d234a8ee58`
- `deploy/docker-compose.prod.yml` yr.arb block patched with `YIELD_ROT_OPERATOR_PK` + unprefixed `NAV_ORACLE_PK: ${YIELD_ROT_NAV_ORACLE_PK}` overrides.

Remaining cleanup:
- yr.kite Variant 2/3 vaults — operator still = deployer on-chain (services not running); rotate same way if you want operator parity.
- Bare `OPERATOR_PK` / `NAV_ORACLE_PK` env vars in `/srv/helios/.env` — safe to delete once every running service has its dedicated override in the compose file (all four do as of 2026-05-14).

Full runbook (funding amounts, exact cast commands, verification) lives in `memory/project_deployer_pk_signer_collapse.md`.

⚠️ **Operational gas state:**
- Kite: deployer balance ~0.30 KITE, drains ~0.00006 KITE/min, ~85h to drain. Not urgent.
- Base oracle signer (`0x32b0112C…`): gas-starved, ~0.0006 ETH; needs faucet top-up.
- Arb oracle signer (`0x32b0112C…`): funded 0.02 ETH; healthy.
