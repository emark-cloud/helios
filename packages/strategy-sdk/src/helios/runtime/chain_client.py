"""Resilient Web3 HTTP client for the strategy runtime.

The live strategies dial a single JSON-RPC endpoint
(`rpc-testnet.gokite.ai`) every bar for the NAV seed
(`IERC20.balanceOf(vault)`) and the `reportNAV` / `executeWithProof`
submits. That endpoint is a pooled set of backends, some of which
intermittently close the connection mid-request — surfacing as
``urllib3`` ``ProtocolError`` / ``RemoteDisconnected`` and logged by the
runtime as ``*.nav.seed_failed`` / ``*.nav.submit_failed``. A dropped
bar is a missed trade opportunity, so the connection should be retried
with backoff before the bar gives up rather than failing on the first
flake.

`build_resilient_web3` returns a `Web3` whose underlying `requests`
session mounts a `urllib3` `Retry` adapter. JSON-RPC is POST, and the
default `Retry` only retries idempotent methods, so retries are enabled
for *all* methods: every read we issue (`eth_call`, `eth_blockNumber`,
`eth_getTransactionCount`) is idempotent, and a re-broadcast of an
already-signed raw transaction is a no-op on-chain (same nonce — the
node returns "already known" / "nonce too low", it does not double
execute). This makes method-agnostic connection retry safe here.

Tunable via env without a code change (infra knob, not strategy
behavior — does not touch any signal/threshold):
  * ``STRATEGY_RPC_RETRIES``  — total attempts per failure class (default 4)
  * ``STRATEGY_RPC_BACKOFF``  — urllib3 backoff factor seconds (default 0.5)
  * ``STRATEGY_RPC_TIMEOUT``  — per-request timeout seconds (default 20)

This subpackage keeps the SDK's no-workspace-deps contract:
`requests`/`urllib3` arrive transitively with `web3` (a public PyPI
dependency), nothing else is imported.
"""

from __future__ import annotations

import os

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from web3 import Web3


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _build_retry(total: int, backoff_factor: float) -> Retry:
    # `allowed_methods=False` is urllib3's documented sentinel for
    # "retry on every method" (JSON-RPC is POST, which the default
    # idempotent-only allowlist would skip). The stubs type the param
    # as `Collection[str] | None` and omit the `False` sentinel, so the
    # one ignore below is the sentinel, not a real type hole.
    # urllib3 >= 1.26 renamed `method_whitelist` -> `allowed_methods`.
    try:
        return Retry(
            total=total,
            connect=total,
            read=total,
            status=total,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            raise_on_status=False,
            respect_retry_after_header=True,
            allowed_methods=False,  # type: ignore[arg-type]
        )
    except TypeError:  # pragma: no cover - very old urllib3
        return Retry(
            total=total,
            connect=total,
            read=total,
            status=total,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            raise_on_status=False,
            respect_retry_after_header=True,
            method_whitelist=False,  # type: ignore[call-arg]
        )


def build_resilient_web3(
    rpc_url: str,
    *,
    total_retries: int | None = None,
    backoff_factor: float | None = None,
    timeout: float | None = None,
) -> Web3:
    """Return a `Web3` over an HTTP provider that retries transient
    connection / 5xx failures with exponential backoff.

    Argument values win over env; env wins over the built-in default.
    """
    retries = total_retries if total_retries is not None else _env_int("STRATEGY_RPC_RETRIES", 4)
    backoff = (
        backoff_factor if backoff_factor is not None else _env_float("STRATEGY_RPC_BACKOFF", 0.5)
    )
    req_timeout = timeout if timeout is not None else _env_float("STRATEGY_RPC_TIMEOUT", 20.0)

    session = Session()
    adapter = HTTPAdapter(max_retries=_build_retry(retries, backoff))
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return Web3(
        Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": req_timeout}, session=session)
    )
