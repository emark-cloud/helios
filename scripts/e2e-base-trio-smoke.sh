#!/usr/bin/env bash
# Phase-3 follow-up smoke check — confirms the new base trio + the
# UserVault/AllocatorVault impl swap are live and healthy on Kite testnet.
# Read-only (no transactions). Safe to run repeatedly.
#
# Env (at least one path to KITE_RPC_URL needs to resolve):
#   KITE_RPC_URL   default read from .env
#
# Optional:
#   DEPLOYMENTS    default contracts/deployments/kite-testnet.json

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${KITE_RPC_URL:-}" && -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; . .env; set +a
fi

if [[ -z "${KITE_RPC_URL:-}" ]]; then
  echo "error: KITE_RPC_URL not set (and not present in .env)" >&2
  exit 2
fi

DEPLOYMENTS="${DEPLOYMENTS:-contracts/deployments/kite-testnet.json}"

uv run --project services/sentinel python scripts/e2e_base_trio_smoke.py \
  --rpc-url "$KITE_RPC_URL" \
  --deployments "$DEPLOYMENTS"
