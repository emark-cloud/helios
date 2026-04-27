#!/usr/bin/env bash
# WS3 — Phase 1 e2e scenario (Track A canonical, Track B opt-in).
#
# Track A (default): boots a local anvil-kite, runs DeployPhase1, drives
# the full vertical slice via scripts/e2e_scenario.py, asserts the
# permissionless-defund hard gate (Helios.md §6.3).
#
# Track B: `RPC_URL=$KITE_RPC_URL DEPLOYER_PK=... ./scripts/e2e-scenario.sh`
# broadcasts the deploy + scenario to Kite testnet. Skips local anvil
# bootstrap; populates contracts/deployments/kite-testnet.json.
#
# Env knobs:
#   RPC_URL            default http://127.0.0.1:8545
#   DEPLOYER_PK        default = anvil[0]  (omit on Track A)
#   OUT_LABEL          default = anvil-kite (set to kite-testnet on Track B)
#   SKIP_ANVIL_BOOT    set to skip the local anvil spin-up (Track B / CI compose)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RPC_URL="${RPC_URL:-http://127.0.0.1:8545}"
DEPLOYER_PK="${DEPLOYER_PK:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
OUT_LABEL="${OUT_LABEL:-anvil-kite}"
DEPLOYMENTS_FILE="contracts/deployments/${OUT_LABEL}.json"

ANVIL_PID=""
cleanup() {
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
      >/tmp/helios-e2e-anvil.log 2>&1 &
    ANVIL_PID=$!
    sleep 1
  else
    echo "[e2e] anvil-kite already up; reusing"
  fi
fi

# ── 2. deploy ─────────────────────────────────────────────────────
echo "[e2e] forge script DeployPhase1 → $DEPLOYMENTS_FILE"
rm -f "$DEPLOYMENTS_FILE"
(
  cd contracts
  DEPLOYER_PK="$DEPLOYER_PK" OUT_LABEL="$OUT_LABEL" \
    forge script script/DeployPhase1.s.sol \
    --rpc-url "$RPC_URL" --broadcast --silent
) >/tmp/helios-e2e-deploy.log 2>&1 || {
  echo "[e2e] deploy failed; tail of log:"
  tail -50 /tmp/helios-e2e-deploy.log
  exit 1
}

if [[ ! -f "$DEPLOYMENTS_FILE" ]]; then
  echo "[e2e] FAILED: $DEPLOYMENTS_FILE not written"
  exit 1
fi
echo "[e2e] deployed; addresses at $DEPLOYMENTS_FILE"

# ── 3. drive scenario ─────────────────────────────────────────────
echo "[e2e] driving scenario..."
RPC_URL="$RPC_URL" DEPLOYMENTS_FILE="$DEPLOYMENTS_FILE" \
  uv run --package helios-sentinel python scripts/e2e_scenario.py \
  --rpc-url "$RPC_URL" --deployments "$DEPLOYMENTS_FILE"

echo "[e2e] WS3 acceptance: GREEN"
