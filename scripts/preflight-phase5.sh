#!/usr/bin/env bash
# Phase 5 / WS8 — pre-demo health check.
#
# For each venue the demo touches, query a minimum-viability signal
# directly from chain via `cast` and emit a per-strategy verdict:
# `REAL` if the live venue clears the threshold, `MOCK` if it doesn't.
# The runbook reads this output and sets `HELIOS_VENUE_<chain>=...`
# before kicking off `e2e-scenario.sh phase5`.
#
# Thresholds:
#   - Base Sepolia / Uniswap V3: pool `liquidity()` ≥ MIN_UNIV3_LIQUIDITY
#     (default 10**15 — pool depth > 1e-3 of a token with 18 decimals;
#     real ETH/USDC pools sit several orders of magnitude above this).
#   - Arbitrum Sepolia / Aave V3: `currentLiquidityRate(asset)` > 0
#     (a flat zero rate means the reserve is paused or empty; any
#     non-zero rate is enough for the rotation strategy to pick a side).
#   - Kite testnet / OraclePriceAnchor: `freshness(latest)` returns
#     within MAX_ORACLE_STALENESS_SEC (default 600). Implementation
#     reuses the signed root from the deployment JSON.
#
# Inputs (env, all optional — missing vars switch the corresponding leg
# to MOCK with an explicit "WS2 broadcast pending" reason):
#   KITE_RPC_URL                 (required for the Kite leg; default = .env)
#   BASE_SEPOLIA_RPC_URL         (required for the Base leg)
#   ARBITRUM_SEPOLIA_RPC_URL     (required for the Arb leg)
#   BASE_DEPLOYMENTS_FILE        default contracts/deployments/base-sepolia.json
#   ARB_DEPLOYMENTS_FILE         default contracts/deployments/arbitrum-sepolia.json
#   KITE_DEPLOYMENTS_FILE        default contracts/deployments/kite-testnet.json
#   BASE_UNIV3_POOL              UniV3 pool to probe (defaults to ETH/USDC 0.05% on Base Sepolia)
#   ARB_AAVE_RESERVE             Aave reserve to probe (defaults to USDC on Arb Sepolia)
#   MIN_UNIV3_LIQUIDITY          default 1000000000000000  (1e15)
#   MAX_ORACLE_STALENESS_SEC     default 600
#
# Output:
#   stdout — one `VENUE_<chain>=<REAL|MOCK> reason=<...>` line per leg
#            and a final summary block. Exit 0 always — the script's
#            job is to *report*, not to gate; the runbook decides what
#            to do with the verdict.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

KITE_DEPLOYMENTS_FILE="${KITE_DEPLOYMENTS_FILE:-contracts/deployments/kite-testnet.json}"
BASE_DEPLOYMENTS_FILE="${BASE_DEPLOYMENTS_FILE:-contracts/deployments/base-sepolia.json}"
ARB_DEPLOYMENTS_FILE="${ARB_DEPLOYMENTS_FILE:-contracts/deployments/arbitrum-sepolia.json}"

# Canonical Sepolia testnet pools — verified at deploy time via
# `UniswapV3Factory.getPool` / Aave docs (2026-05-08).
BASE_UNIV3_POOL="${BASE_UNIV3_POOL:-0x4e96ed40b3da019B6764C30aA2c66B72be51DA31}"
# USDC on Arbitrum Sepolia (Aave V3 reserve symbol = USDC). Override
# via env if the demo uses a different reserve.
ARB_AAVE_RESERVE="${ARB_AAVE_RESERVE:-0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d}"

MIN_UNIV3_LIQUIDITY="${MIN_UNIV3_LIQUIDITY:-1000000000000000}"
MAX_ORACLE_STALENESS_SEC="${MAX_ORACLE_STALENESS_SEC:-600}"

declare -A VERDICT
declare -A REASON

# ── helpers ─────────────────────────────────────────────────────────
have_cast=1
if ! command -v cast >/dev/null 2>&1; then
  have_cast=0
fi

read_addr_from_json() {
  # Tolerant JSON read — preflight runs on operator laptops where `jq`
  # may not be installed, so we shell out to python for the read.
  local file="$1"
  local key="$2"
  if [[ ! -f "$file" ]]; then
    echo ""
    return
  fi
  python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('addresses', {}).get(sys.argv[2], '') or '')
except Exception:
    print('')
" "$file" "$key"
}

# ── 1. Base Sepolia / Uniswap V3 ────────────────────────────────────
chain="base"
if [[ -z "${BASE_SEPOLIA_RPC_URL:-}" ]]; then
  VERDICT[$chain]="MOCK"
  REASON[$chain]="BASE_SEPOLIA_RPC_URL unset"
elif [[ "$have_cast" -eq 0 ]]; then
  VERDICT[$chain]="MOCK"
  REASON[$chain]="cast unavailable; install foundry"
else
  liq=$(cast call "$BASE_UNIV3_POOL" 'liquidity()(uint128)' \
        --rpc-url "$BASE_SEPOLIA_RPC_URL" 2>/dev/null \
        | awk '{print $1}' \
        | sed 's/\[.*\]//')
  if [[ -z "$liq" || "$liq" == "0" ]]; then
    VERDICT[$chain]="MOCK"
    REASON[$chain]="UniV3 pool $BASE_UNIV3_POOL returned no liquidity (paused or empty)"
  elif python3 -c "import sys; sys.exit(0 if int(sys.argv[1]) >= int(sys.argv[2]) else 1)" \
       "$liq" "$MIN_UNIV3_LIQUIDITY"; then
    VERDICT[$chain]="REAL"
    REASON[$chain]="UniV3 liquidity=$liq ≥ $MIN_UNIV3_LIQUIDITY"
  else
    VERDICT[$chain]="MOCK"
    REASON[$chain]="UniV3 liquidity=$liq below threshold $MIN_UNIV3_LIQUIDITY"
  fi
fi

# ── 2. Arbitrum Sepolia / Aave V3 ───────────────────────────────────
chain="arbitrum"
if [[ -z "${ARBITRUM_SEPOLIA_RPC_URL:-}" ]]; then
  VERDICT[$chain]="MOCK"
  REASON[$chain]="ARBITRUM_SEPOLIA_RPC_URL unset"
elif [[ "$have_cast" -eq 0 ]]; then
  VERDICT[$chain]="MOCK"
  REASON[$chain]="cast unavailable; install foundry"
else
  arb_pool=$(read_addr_from_json "$ARB_DEPLOYMENTS_FILE" "aavePool")
  if [[ -z "$arb_pool" ]]; then
    arb_pool="0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff"
    REASON[$chain]="WS2 broadcast pending — using canonical Aave V3 Pool"
  fi
  rate=$(cast call "$arb_pool" 'currentLiquidityRate(address)(uint256)' "$ARB_AAVE_RESERVE" \
         --rpc-url "$ARBITRUM_SEPOLIA_RPC_URL" 2>/dev/null \
         | awk '{print $1}' \
         | sed 's/\[.*\]//')
  if [[ -z "$rate" || "$rate" == "0" ]]; then
    VERDICT[$chain]="MOCK"
    REASON[$chain]="Aave reserve $ARB_AAVE_RESERVE returned zero liquidity rate (paused or empty)"
  else
    VERDICT[$chain]="REAL"
    REASON[$chain]="Aave currentLiquidityRate=$rate (non-zero)"
  fi
fi

# ── 3. Kite / OraclePriceAnchor ─────────────────────────────────────
chain="kite"
if [[ -z "${KITE_RPC_URL:-}" ]]; then
  VERDICT[$chain]="MOCK"
  REASON[$chain]="KITE_RPC_URL unset"
elif [[ "$have_cast" -eq 0 ]]; then
  VERDICT[$chain]="MOCK"
  REASON[$chain]="cast unavailable; install foundry"
else
  oracle_addr=$(read_addr_from_json "$KITE_DEPLOYMENTS_FILE" "oraclePriceAnchor")
  if [[ -z "$oracle_addr" ]]; then
    VERDICT[$chain]="MOCK"
    REASON[$chain]="oraclePriceAnchor missing from $KITE_DEPLOYMENTS_FILE"
  else
    # `latestRoot()` returns the Poseidon root posted most recently —
    # if the contract is healthy this returns non-zero. Freshness check
    # is a follow-up against `committedAt(root)` once a root is in hand.
    latest=$(cast call "$oracle_addr" 'latestRoot()(bytes32)' \
             --rpc-url "$KITE_RPC_URL" 2>/dev/null \
             | awk '{print $1}')
    if [[ -z "$latest" || "$latest" == "0x0000000000000000000000000000000000000000000000000000000000000000" ]]; then
      VERDICT[$chain]="MOCK"
      REASON[$chain]="oracle has no committed root yet"
    else
      committed_at=$(cast call "$oracle_addr" 'committedAt(bytes32)(uint64)' "$latest" \
                     --rpc-url "$KITE_RPC_URL" 2>/dev/null \
                     | awk '{print $1}' \
                     | sed 's/\[.*\]//')
      now=$(date +%s)
      if [[ -z "$committed_at" || "$committed_at" == "0" ]]; then
        VERDICT[$chain]="MOCK"
        REASON[$chain]="oracle committedAt unreadable for latest root"
      else
        age=$(( now - committed_at ))
        if [[ "$age" -le "$MAX_ORACLE_STALENESS_SEC" ]]; then
          VERDICT[$chain]="REAL"
          REASON[$chain]="oracle root age=${age}s ≤ ${MAX_ORACLE_STALENESS_SEC}s"
        else
          VERDICT[$chain]="MOCK"
          REASON[$chain]="oracle stale (age=${age}s > ${MAX_ORACLE_STALENESS_SEC}s) — service may be down"
        fi
      fi
    fi
  fi
fi

# ── Output ──────────────────────────────────────────────────────────
echo "# Phase 5 preflight — $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
for chain in base arbitrum kite; do
  echo "VENUE_${chain^^}=${VERDICT[$chain]} reason=\"${REASON[$chain]}\""
done

# Demo runbook hints — copy into the operator's shell to wire the
# right venue per chain into the e2e-scenario phase5 invocation.
echo ""
echo "# Suggested env for the demo run:"
echo "export HELIOS_VENUE_BASE=${VERDICT[base]}"
echo "export HELIOS_VENUE_ARBITRUM=${VERDICT[arbitrum]}"
echo "export HELIOS_VENUE_KITE=${VERDICT[kite]}"

# Always exit 0 — the runbook (not the script) decides whether a MOCK
# verdict aborts the demo. A non-zero exit here would conflate "venue
# unhealthy" with "script broken".
exit 0
