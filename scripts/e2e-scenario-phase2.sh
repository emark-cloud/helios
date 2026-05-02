#!/usr/bin/env bash
# WS6 — Phase 2 e2e scenario (Track A canonical, Track B opt-in).
#
# Boots a local anvil-kite, runs the full Phase 2 deploy pipeline
# (DeployPhase1 → DeployPhase2 → RegisterPhase2Strategies), then drives
# the multi-class scenario via scripts/e2e_scenario_phase2.py:
#
#   user signs meta-strategy with all 3 classes allowed
#   → deposit + delegate
#   → operator allocates across all 6 strategies (2 per class)
#   → smoke-asserts the deploy + 6 allocations landed.
#
# This is the PR1 skeleton: no trades, no proofs, no reputation
# assertions yet. PR2 layers real Groth16 proof generation on top;
# PR3 adds the §8.2 reputation assertions; PR3.5 bakes in the
# WS7.A rotateParams + WS7.B bootstrap-allocation extensions.
#
# Track A (default): RPC stays on the local anvil; OUT_LABEL is
# `anvil-kite-phase2` so we don't clobber the Phase 1 e2e's
# `anvil-kite.json`.
#
# Track B: `RPC_URL=$KITE_RPC_URL DEPLOYER_PK=... \
#   OUT_LABEL=kite-testnet ./scripts/e2e-scenario-phase2.sh` broadcasts
# to Kite testnet. The merge logic in DeployPhase2 / RegisterPhase2
# tolerates pre-existing Phase 1 keys in `kite-testnet.json`.
#
# Env knobs:
#   RPC_URL            default http://127.0.0.1:8545
#   DEPLOYER_PK        default = anvil[0]
#   OUT_LABEL          default = anvil-kite-phase2
#   SKIP_ANVIL_BOOT    set to skip anvil spin-up

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RPC_URL="${RPC_URL:-http://127.0.0.1:8545}"
DEPLOYER_PK="${DEPLOYER_PK:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
OUT_LABEL="${OUT_LABEL:-anvil-kite-phase2}"
DEPLOYMENTS_FILE="contracts/deployments/${OUT_LABEL}.json"

PROVER_HTTP_PORT="${PROVER_HTTP_PORT:-8004}"
PROVER_URL="${PROVER_URL:-http://127.0.0.1:${PROVER_HTTP_PORT}}"

ANVIL_PID=""
PROVER_PID=""
cleanup() {
  if [[ -n "$PROVER_PID" ]] && kill -0 "$PROVER_PID" 2>/dev/null; then
    echo "[e2e] stopping prover (pid=$PROVER_PID)"
    kill "$PROVER_PID" 2>/dev/null || true
    wait "$PROVER_PID" 2>/dev/null || true
  fi
  if [[ -n "$ANVIL_PID" ]] && kill -0 "$ANVIL_PID" 2>/dev/null; then
    echo "[e2e] stopping anvil (pid=$ANVIL_PID)"
    kill "$ANVIL_PID" 2>/dev/null || true
    wait "$ANVIL_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ── 1. anvil-kite ─────────────────────────────────────────────────
if [[ -z "${SKIP_ANVIL_BOOT:-}" && "$RPC_URL" == "http://127.0.0.1:8545" ]]; then
  if ! curl -sf -m 1 -X POST -H 'content-type: application/json' \
        --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' \
        "$RPC_URL" >/dev/null 2>&1; then
    echo "[e2e] booting anvil-kite (chainId=2368, 1s blocks)"
    anvil --host 127.0.0.1 --chain-id 2368 --port 8545 --block-time 1 \
      >/tmp/helios-e2e-phase2-anvil.log 2>&1 &
    ANVIL_PID=$!
    sleep 1
  else
    echo "[e2e] anvil-kite already up; reusing"
  fi
fi

# ── 2. DeployPhase1 ───────────────────────────────────────────────
echo "[e2e] forge script DeployPhase1 → $DEPLOYMENTS_FILE"
rm -f "$DEPLOYMENTS_FILE"
(
  cd contracts
  DEPLOYER_PK="$DEPLOYER_PK" OUT_LABEL="$OUT_LABEL" \
    forge script script/DeployPhase1.s.sol \
    --rpc-url "$RPC_URL" --broadcast --silent
) >/tmp/helios-e2e-phase2-deploy1.log 2>&1 || {
  echo "[e2e] Phase 1 deploy failed; tail of log:"
  tail -50 /tmp/helios-e2e-phase2-deploy1.log
  exit 1
}
[[ -f "$DEPLOYMENTS_FILE" ]] || { echo "[e2e] FAILED: $DEPLOYMENTS_FILE not written"; exit 1; }

# Extract Phase 1 addresses we need to feed Phase 2.
read_addr() {
  python3 -c "import json,sys; print(json.load(open('$DEPLOYMENTS_FILE'))['addresses']['$1'])"
}
USDC_ADDR=$(read_addr usdc)
SWAP_ROUTER_ADDR=$(read_addr swapRouter)
STRATEGY_REGISTRY_ADDR=$(read_addr strategyRegistry)
ALLOCATOR_REGISTRY_ADDR=$(read_addr allocatorRegistry)
ALLOCATOR_VAULT_ADDR=$(read_addr allocatorVault)
TRADE_VERIFIER_ADDR=$(read_addr tradeAttestationVerifier)
DEPLOYER_ADDR=$(python3 -c "from eth_account import Account; print(Account.from_key('$DEPLOYER_PK').address)" 2>/dev/null \
  || cast wallet address --private-key "$DEPLOYER_PK")

# ── 3. DeployPhase2 ───────────────────────────────────────────────
echo "[e2e] forge script DeployPhase2 → $DEPLOYMENTS_FILE (layered)"
(
  cd contracts
  DEPLOYER_PK="$DEPLOYER_PK" \
    TRADE_VERIFIER="$TRADE_VERIFIER_ADDR" \
    STRATEGY_REGISTRY="$STRATEGY_REGISTRY_ADDR" \
    ALLOCATOR_REGISTRY="$ALLOCATOR_REGISTRY_ADDR" \
    REP_SIGNER="$DEPLOYER_ADDR" \
    OUT_LABEL="$OUT_LABEL" \
    forge script script/DeployPhase2.s.sol \
    --rpc-url "$RPC_URL" --broadcast --silent
) >/tmp/helios-e2e-phase2-deploy2.log 2>&1 || {
  echo "[e2e] Phase 2 deploy failed; tail of log:"
  tail -50 /tmp/helios-e2e-phase2-deploy2.log
  exit 1
}

# ── 4. RegisterPhase2Strategies ──────────────────────────────────
echo "[e2e] forge script RegisterPhase2Strategies → $DEPLOYMENTS_FILE (layered)"
(
  cd contracts
  DEPLOYER_PK="$DEPLOYER_PK" \
    USDC="$USDC_ADDR" \
    STRATEGY_REGISTRY="$STRATEGY_REGISTRY_ADDR" \
    ALLOCATOR_VAULT="$ALLOCATOR_VAULT_ADDR" \
    TRADE_VERIFIER="$TRADE_VERIFIER_ADDR" \
    SWAP_ROUTER="$SWAP_ROUTER_ADDR" \
    OUT_LABEL="$OUT_LABEL" \
    forge script script/RegisterPhase2Strategies.s.sol \
    --rpc-url "$RPC_URL" --broadcast --silent
) >/tmp/helios-e2e-phase2-register.log 2>&1 || {
  echo "[e2e] RegisterPhase2 failed; tail of log:"
  tail -50 /tmp/helios-e2e-phase2-register.log
  exit 1
}
echo "[e2e] deploy+register pipeline complete; addresses at $DEPLOYMENTS_FILE"

# ── 4.5. RegisterFreshStrategy (PR3.5.C) ─────────────────────────
# Bolts on a 7th vault (`strategyVaultMomentumVariant3`) with zero
# track record so the WS7.B sentinel bootstrap pool has something
# to allocate cold-start capital to in step_drive_bootstrap_pool.
echo "[e2e] forge script RegisterFreshStrategy → $DEPLOYMENTS_FILE (layered)"
(
  cd contracts
  DEPLOYER_PK="$DEPLOYER_PK" \
    USDC="$USDC_ADDR" \
    STRATEGY_REGISTRY="$STRATEGY_REGISTRY_ADDR" \
    ALLOCATOR_VAULT="$ALLOCATOR_VAULT_ADDR" \
    TRADE_VERIFIER="$TRADE_VERIFIER_ADDR" \
    SWAP_ROUTER="$SWAP_ROUTER_ADDR" \
    OUT_LABEL="$OUT_LABEL" \
    forge script script/RegisterFreshStrategy.s.sol \
    --rpc-url "$RPC_URL" --broadcast --silent
) >/tmp/helios-e2e-phase2-fresh.log 2>&1 || {
  echo "[e2e] RegisterFreshStrategy failed; tail of log:"
  tail -50 /tmp/helios-e2e-phase2-fresh.log
  exit 1
}

# ── 5. prover service ────────────────────────────────────────────
# PR2.A onwards drives real Groth16 proofs against the registered
# verifiers. The prover wraps snarkjs.fullProve and reads the .wasm /
# .zkey artifacts from circuits/build/<class>/ — those are checked in,
# no rebuild needed. Skip-flag for CI-level boots that pre-spawn it.
if [[ -z "${SKIP_PROVER_BOOT:-}" ]]; then
  if ! curl -sf -m 1 "$PROVER_URL/health" >/dev/null 2>&1; then
    echo "[e2e] booting prover (port=$PROVER_HTTP_PORT)"
    PROVER_HTTP_PORT="$PROVER_HTTP_PORT" \
      node services/prover/src/index.js \
      >/tmp/helios-e2e-phase2-prover.log 2>&1 &
    PROVER_PID=$!
    # Wait for /health — snarkjs imports + circuit registration take ~1-2s.
    for _ in $(seq 1 30); do
      if curl -sf -m 1 "$PROVER_URL/health" >/dev/null 2>&1; then break; fi
      sleep 0.5
    done
    if ! curl -sf -m 1 "$PROVER_URL/health" >/dev/null 2>&1; then
      echo "[e2e] prover failed to come up; tail of log:"
      tail -30 /tmp/helios-e2e-phase2-prover.log
      exit 1
    fi
  else
    echo "[e2e] prover already up; reusing"
  fi
fi

# ── 6. drive scenario ─────────────────────────────────────────────
echo "[e2e] driving Phase 2 scenario..."
RPC_URL="$RPC_URL" DEPLOYMENTS_FILE="$DEPLOYMENTS_FILE" PROVER_URL="$PROVER_URL" \
  uv run --package helios-sentinel python scripts/e2e_scenario_phase2.py \
  --rpc-url "$RPC_URL" --deployments "$DEPLOYMENTS_FILE" \
  --prover-url "$PROVER_URL"

echo "[e2e] WS6 PR3.5.C acceptance: GREEN"
