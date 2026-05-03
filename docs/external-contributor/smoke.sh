#!/usr/bin/env bash
# External-contributor smoke — closes Phase 2 acceptance gate
# "External contributor could publish using only SDK + public docs."
#
# Builds the smoke image (PR5.A: from local workspace; PR5.B: from
# test-PyPI when INSTALL_MODE=testpypi is set), then runs the two CLI
# commands a brand-new contributor's first session would touch:
#   1. `helios backtest` — proves the SDK + CLI talk to the backtest
#      engine and produce a markdown report.
#   2. `helios simulate` — proves the same pipeline at sub-second
#      cadence, suitable as a CI smoke for downstream strategy repos.
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
IMAGE_TAG="${IMAGE_TAG:-helios-sdk-smoke:${INSTALL_MODE}}"

echo "▶ Building smoke image (${IMAGE_TAG}, INSTALL_MODE=${INSTALL_MODE})"
docker build \
    --file "${DOCKERFILE}" \
    --build-arg "INSTALL_MODE=${INSTALL_MODE}" \
    --build-arg "SDK_VERSION=${SDK_VERSION}" \
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
