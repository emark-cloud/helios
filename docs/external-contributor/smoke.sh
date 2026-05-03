#!/usr/bin/env bash
# External-contributor smoke — closes Phase 2 acceptance gate
# "External contributor could publish using only SDK + public docs."
#
# Builds the smoke image and runs the two CLI commands a brand-new
# contributor's first session would touch:
#   1. `helios backtest` — proves the SDK + CLI talk to the backtest
#      engine and produce a markdown report.
#   2. `helios simulate` — proves the same pipeline at sub-second
#      cadence, suitable as a CI smoke for downstream strategy repos.
#
# Install modes (set via INSTALL_MODE env var):
#   local    — COPY workspace packages and pip-install. Default; no
#              network publish needed.
#   release  — fetch the four wheels from a GitHub Release and pip
#              install via --find-links. Set WHEEL_BASE_URL to the
#              release-asset directory URL (e.g.
#              https://github.com/<owner>/<repo>/releases/download/sdk-v0.1.0/).
#              This is the canonical PR5.B path — independent of
#              test.pypi.org availability.
#   testpypi — pip install from test-PyPI (gated on the trusted-publisher
#              entries for helios-trader-cli / helios-allocator-sdk /
#              helios-contracts-abi being registered).
#
# `helios test-proof` requires a live prover service + circuit
# artifacts; it's exercised separately in the WS6 e2e (PR2.* commits).
# The smoke deliberately stays self-contained so a fresh contributor
# can run it on a laptop with only Docker installed.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="${REPO_ROOT}/docs/external-contributor/Dockerfile"
INSTALL_MODE="${INSTALL_MODE:-local}"
SDK_VERSION="${SDK_VERSION:-0.1.0}"
WHEEL_BASE_URL="${WHEEL_BASE_URL:-}"
IMAGE_TAG="${IMAGE_TAG:-helios-sdk-smoke:${INSTALL_MODE}}"

if [ "$INSTALL_MODE" = "release" ] && [ -z "$WHEEL_BASE_URL" ]; then
    echo "INSTALL_MODE=release requires WHEEL_BASE_URL=<github-release-asset-dir-url>" >&2
    exit 1
fi

echo "▶ Building smoke image (${IMAGE_TAG}, INSTALL_MODE=${INSTALL_MODE})"
docker build \
    --file "${DOCKERFILE}" \
    --build-arg "INSTALL_MODE=${INSTALL_MODE}" \
    --build-arg "SDK_VERSION=${SDK_VERSION}" \
    --build-arg "WHEEL_BASE_URL=${WHEEL_BASE_URL}" \
    --tag "${IMAGE_TAG}" \
    "${REPO_ROOT}"

echo
echo "▶ helios backtest examples/minimal_momentum.py --period 7d"
docker run --rm "${IMAGE_TAG}" backtest \
    --strategy /opt/helios/examples/minimal_momentum.py \
    --period 7d \
    --output-dir /tmp/backtests

echo
echo "▶ helios simulate examples/minimal_momentum.py --minutes 30"
docker run --rm "${IMAGE_TAG}" simulate \
    --strategy /opt/helios/examples/minimal_momentum.py \
    --minutes 30

echo
echo "✓ Smoke green — external-contributor flow works end-to-end."
