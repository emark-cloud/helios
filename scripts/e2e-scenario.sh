#!/usr/bin/env bash
# e2e mode dispatcher. Runs the live Phase-5/6 acceptance harnesses
# against an already-deployed stack — no local anvil, no Phase-1
# bootstrap. The Phase-1/2 e2e Track was retired with the cleanup
# of `scripts/e2e_scenario*.py` and `contracts/script/DeployPhase{1,2}`.
#
# Modes:
#   phase5           — Phase-5 cross-chain dispatcher acceptance test.
#   phase6-realprice — Phase-6 real-price cutover acceptance harness.
#
# Env knobs:
#   KITE_RPC_URL                Defaults to https://rpc-testnet.gokite.ai/.
#   DEPLOYMENTS_FILE            Defaults to contracts/deployments/kite-testnet.json.
#   HELIOS_VENUE_BASE / HELIOS_VENUE_ARBITRUM / HELIOS_VENUE_KITE
#                               `REAL` or `MOCK` per chain (phase5 mode).
#                               Default MOCK so CI is not coupled to
#                               live testnet liquidity; demo runs flip
#                               these via preflight output.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:-}"
if [[ -z "$MODE" ]]; then
  echo "usage: $0 {phase5|phase6-realprice}" >&2
  exit 2
fi

case "$MODE" in
  phase6-realprice)
    echo "[e2e] phase6-realprice — running real-price cutover acceptance harness"
    KITE_RPC_URL="${KITE_RPC_URL:-https://rpc-testnet.gokite.ai/}" \
    DEPLOYMENTS_FILE="${DEPLOYMENTS_FILE:-contracts/deployments/kite-testnet.json}" \
      uv run --package helios-sentinel python scripts/e2e_phase6_realprice.py
    echo "[e2e] phase6-realprice acceptance: GREEN"
    ;;
  phase5)
    echo "[e2e] phase5 — running cross-chain dispatcher acceptance test"
    HELIOS_VENUE_BASE="${HELIOS_VENUE_BASE:-MOCK}" \
    HELIOS_VENUE_ARBITRUM="${HELIOS_VENUE_ARBITRUM:-MOCK}" \
    HELIOS_VENUE_KITE="${HELIOS_VENUE_KITE:-MOCK}" \
      uv run --package helios-sentinel \
        pytest -q services/sentinel/tests/test_phase5_xchain.py
    echo "[e2e] phase5 acceptance: GREEN"
    ;;
  *)
    echo "unknown mode: $MODE" >&2
    echo "usage: $0 {phase5|phase6-realprice}" >&2
    exit 2
    ;;
esac
