# Local testing — Phase 1 frontend

How to exercise the Phase 1 vertical slice (`v0.1.0-phase1`) on your laptop. Three tiers, increasing setup cost.

| Tier | Setup time | What you can test | Best for |
|---|---|---|---|
| **1** — Page-level smoke | ≈ 5 min | All three pages render; `/strategies` populated against live Goldsky | Visual QA, design review, hotkey checks, `/strategies` data binding |
| **2** — Full local stack | ≈ 15–20 min | Writable flows: `/onboard` persists meta-strategies, `/dashboard` shows live allocations + WebSocket events | Hand-stepping the user journey |
| **3** — Drive auto-defund | + 5 min on Tier 2 | One-shot scenario: deposit → allocate → drawdown → permissionless defund → reallocate | Seeing the cascade + defund moment land |

The Goldsky subgraph (`helios/v0.1.1`) is **already live and indexing the Track B addresses**, so Tier 1 needs zero backend setup.

---

## Tier 1 — Page-level smoke

```bash
cd /home/emark/helios/frontend
cat > .env.local <<'EOF'
NEXT_PUBLIC_GOLDSKY_ENDPOINT=https://api.goldsky.com/api/public/project_cmodpmbv1pkd70127d9g741ek/subgraphs/helios/v0.1.1/gn
NEXT_PUBLIC_SENTINEL_URL=http://localhost:8001
EOF
pnpm dev
# open http://localhost:3000
```

What works at Tier 1:

| Page | Status |
|---|---|
| `/` landing | ✅ static |
| `/strategies` | ✅ **fully** — sortable table populated from Track B (3 strategies, real `currentReputation`, real classes) |
| `/dashboard?user=<your-eoa>` | ⚠️ partially — empty top strip until allocations exist; activity rail shows "Connecting to Sentinel…" then reconnects-once-and-stops |
| `/onboard` | ✅ UI works, wallet signature works, **POST to Sentinel will fail gracefully** with a connection error — meta-strategy doesn't actually persist |

Right tier for: visual QA, design review, hotkey checks, `/strategies` data-binding.

---

## Tier 2 — Full local stack with Sentinel

Adds local anvil + DeployPhase1 + the four Python services, so `/onboard` actually persists a meta-strategy and `/dashboard` shows real allocations.

Open **5 terminals** in `/home/emark/helios`:

**T1 — infra**

```bash
docker compose up -d postgres redis
```

**T2 — local Kite anvil + contracts**

Anvil-kite already runs in compose (T1). Skip the bare `anvil` invocation; just deploy:

```bash
cd contracts
OUT_LABEL=anvil-kite \
DEPLOYER_PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
forge script script/DeployPhase1.s.sol \
  --rpc-url http://localhost:8545 \
  --broadcast --skip-simulation
# writes contracts/deployments/anvil-kite.json
```

Two non-obvious flags:

- **`DEPLOYER_PK` env var** — the script reads it via `vm.envUint`, not `--private-key`. `0xac09…ff80` is anvil's first default key.
- **`OUT_LABEL=anvil-kite`** — without it, the script keys on `block.chainid` (2368) and writes to `kite-testnet.json`, **clobbering the live Track B addresses** that judges + Goldsky read from. Always set this for local anvil deploys.

**T3 — services (oracle in scenario mode + reputation + sentinel)**

```bash
export SCENARIO_MODE=1
export RPC_URL=http://localhost:8545
export DEPLOYER_PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
export SENTINEL_OPERATOR_PK=$DEPLOYER_PK
export ORACLE_SIGNER_PK=$DEPLOYER_PK
export REPUTATION_SIGNER_PK=$DEPLOYER_PK

# run each in its own subshell or use a process manager
uv run python -m oracle &           # :8003
uv run python -m reputation &       # :8002
uv run python -m sentinel           # :8001 — keep foreground for logs
```

**T4 — prover** (already in compose from T1, on `:8004`; nothing to start)

**T5 — frontend**

```bash
# .env.local from Tier 1 already points at localhost:8001; restart the dev server
cd frontend && pnpm dev
```

Now end-to-end works:

- `/onboard` → connect EOA → sign meta-strategy → Sentinel persists it
- `/dashboard?user=<your-eoa>` → top strip animates from empty to populated as Sentinel allocates
- Activity rail → live WebSocket events, cascade with 80ms stagger

---

## Tier 3 — Drive the auto-defund scenario

With the Tier 2 stack running, run the scenario script. It deposits, delegates, drives a price drawdown to trigger the permissionless defund, and reallocates. **Note: it's one-shot, not a continuous driver** — refresh the dashboard after it exits to see the events that landed.

```bash
# new terminal, same env as T3
RPC_URL=http://localhost:8545 \
DEPLOYER_PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
SKIP_ANVIL_BOOT=1 \
./scripts/e2e-scenario.sh
```

You'll see in the dashboard activity rail:

- `Allocation` events (with shield icon for proof badge)
- `Defunded` event with red left-border (`data-defund-state="breaching"`)
- `Rebalance complete` event

---

## Recommended order

1. **Run Tier 1 first** to confirm `/strategies` against real Goldsky data — that's the quickest "yes, the frontend works against live Phase 1" check.
2. If `/strategies` looks right, **jump to Tier 3** (it sets up Tier 2 implicitly via `e2e-scenario.sh`'s anvil boot path) for the writable flow + the drawdown moment.
3. Tier 2 alone (without driving the scenario) is mostly useful if you want to step through `/onboard` by hand without the auto-defund interrupting your test.

---

## Gotchas

- **Dashboard is keyed on `?user=0x…`.** With no allocations the page looks empty — that's correct, not broken. To see real data either run Tier 3 (which uses a known test EOA from `e2e_scenario.py`), or visit `/strategies` first.
- **Activity rail does not auto-reconnect.** It opens the WebSocket once, fails once, stays closed. Refresh the page after starting Sentinel to re-subscribe.
- **Lighthouse cold-start TBT.** First request to a fresh `pnpm start` server hits ~890ms TBT (perf 77) due to V8 JIT cold-start; warm up with a curl before measuring.
- **Goldsky pin.** The subgraph is built against `graph-cli@0.83.0` + `graph-ts@0.31.0` + `apiVersion: 0.0.7` (see `subgraph/package.json`). Bumping any of these requires verifying the indexer accepts the WASM — Goldsky's `kite-ai-testnet` runtime rejects opcode 0xFC.
