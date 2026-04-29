"""Poseidon hashing — bit-exact parity with circomlibjs / circom circuits.

Phase 2 swaps the keccak chain in `state.py` for a Poseidon chain so the
momentum/mean-reversion/yield-rotation circuits can consume the oracle
root directly without an extra hash-equivalence proof. circomlibjs is
the canonical Poseidon impl shipped to circom; rather than maintain a
hand-ported Python implementation that has to be re-validated on every
circomlib bump, this module shells out to a long-lived Node helper
(`scripts/poseidon_helper.js`) that wraps `buildPoseidon()`.

The helper is a JSON-line REPL kept warm across calls — circomlibjs's
WASM init cost (~50 ms) is paid once per process. Round-trip per hash
is ~1 ms over a Unix pipe; oracle anchor commits run every 50 blocks so
the throughput requirement is trivial.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

# BN254 scalar field modulus (snark field). All Poseidon outputs are
# reduced into [0, FIELD_MODULUS). Mirrored from circomlibjs.
FIELD_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617

_HELPER_DIR = Path(__file__).resolve().parents[2] / "scripts"
_HELPER_JS = _HELPER_DIR / "poseidon_helper.js"


class PoseidonError(RuntimeError):
    pass


class PoseidonClient:
    """Long-lived subprocess wrapper around `poseidon_helper.js`.

    Thread-safe: a single lock serializes requests over the helper's
    stdin/stdout. The oracle's hot path is single-writer (the poller
    appends snapshots) so contention is negligible; the lock is there to
    keep the protocol safe if a future caller adds parallel readers.
    """

    def __init__(self, node_bin: str | None = None) -> None:
        self._node_bin = node_bin or shutil.which("node") or "node"
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        if not _HELPER_JS.exists():
            raise PoseidonError(f"poseidon helper missing at {_HELPER_JS}")
        env = os.environ.copy()
        # Helper uses circomlibjs from its own node_modules; resolve from cwd.
        proc = subprocess.Popen(
            [self._node_bin, str(_HELPER_JS)],
            cwd=str(_HELPER_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        # First line is the "ready" sentinel; block until we see it so
        # callers don't race the WASM init.
        assert proc.stdout is not None
        ready = proc.stdout.readline()
        if not ready:
            err = proc.stderr.read() if proc.stderr else ""
            raise PoseidonError(f"poseidon helper failed to start: {err.strip()}")
        try:
            payload = json.loads(ready)
        except json.JSONDecodeError as e:
            raise PoseidonError(f"poseidon helper bad ready line: {ready!r}") from e
        if not payload.get("ok") or payload.get("out") != "ready":
            raise PoseidonError(f"poseidon helper not ready: {payload}")
        self._proc = proc
        return proc

    def _request(self, payload: dict[str, object]) -> int:
        with self._lock:
            proc = self._ensure()
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                err = proc.stderr.read() if proc.stderr else ""
                raise PoseidonError(f"poseidon helper closed: {err.strip()}")
            try:
                resp = json.loads(line)
            except json.JSONDecodeError as e:
                raise PoseidonError(f"poseidon helper bad response: {line!r}") from e
            if not resp.get("ok"):
                raise PoseidonError(str(resp.get("err", "unknown error")))
            return int(resp["out"])

    def hash(self, inputs: list[int]) -> int:
        """Poseidon hash of 1..16 field elements. Reduces inputs mod p."""
        if not inputs:
            raise ValueError("hash requires at least one input")
        return self._request({"op": "hash", "inputs": [str(i % FIELD_MODULUS) for i in inputs]})

    def chain(self, inputs: list[int]) -> int:
        """Chained Poseidon: h0 = P(x0); hi = P(h_{i-1}, xi).

        Matches the public-input commitment in `momentum_v1.circom:127-138`
        — the circuit and the oracle MUST agree on this shape so the
        on-chain anchored root is consumable by the verifier directly.
        """
        if not inputs:
            raise ValueError("chain requires at least one input")
        return self._request({"op": "chain", "inputs": [str(i % FIELD_MODULUS) for i in inputs]})

    def close(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    if self._proc.stdin is not None:
                        self._proc.stdin.close()
                except Exception:
                    pass
                try:
                    self._proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None

    def __del__(self) -> None:  # best-effort
        with contextlib.suppress(Exception):
            self.close()


class _Singleton:
    instance: PoseidonClient | None = None
    lock = threading.Lock()


def default_client() -> PoseidonClient:
    """Process-wide singleton. Most callers should use this."""
    with _Singleton.lock:
        if _Singleton.instance is None:
            _Singleton.instance = PoseidonClient()
        return _Singleton.instance


def poseidon_hash(inputs: list[int]) -> int:
    return default_client().hash(inputs)


def poseidon_chain(inputs: list[int]) -> int:
    return default_client().chain(inputs)
