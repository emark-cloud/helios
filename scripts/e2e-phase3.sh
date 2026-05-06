#!/usr/bin/env bash
# WS7 — Phase 3 e2e (Sentinel-vs-Helix divergence + drawdown defund + HWM fee settle).
#
# Pure-Python in-process scenario today. Drives both reference
# allocators (`SentinelAllocator`, `HelixAllocator`) through the SDK's
# `AllocatorRuntime` against a stub Goldsky + dry-run on-chain runner
# and asserts the four Phase 3 acceptance flows from `docs/phase3-plan.md`
# WS7. No anvil, no contracts, no subgraph — same code paths the live
# services run, but composed in Python so it ships in CI under a few
# seconds.
#
# `scenarios/phase3-divergence.py` is the orchestrator; this wrapper
# only manages the venv + invocation pattern so the GH Action and the
# local "is my Phase 3 patch passing the gate?" smoke run share one
# entry point.
#
# Future: when `DeployPhase3` (WS3.B) lands on a refreshed testnet
# pin and Helix is registered alongside Sentinel on a clean anvil-kite
# stack, this script grows the on-chain divergence assertion (boot
# anvil → run deploy pipeline → boot sentinel + helix services →
# replay scenario → assert subgraph state → assert non-zero
# `currentReputation` for both allocators). Tracked as a known
# follow-up.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[e2e-phase3] running scenarios/phase3-divergence.py"

# `services/sentinel` carries the `helios_allocator` + `sentinel` deps
# in its venv; `helix.allocator` is workspace-local and resolves via
# `uv run --project services/sentinel` because `services/helix` is in
# the same workspace lockfile.
uv run --project services/sentinel python scenarios/phase3-divergence.py

echo "[e2e-phase3] OK"
