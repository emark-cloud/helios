"""`build_resilient_web3` — retry/backoff on the strategy chain client.

The live `rpc-testnet.gokite.ai` pool intermittently closes
connections mid-request; without retry a single flake drops a bar's
NAV seed / trade submit. These tests assert the constructed `Web3`
carries a `urllib3` `Retry`-mounted session (POST included, since
JSON-RPC is POST) and that the precedence is arg > env > default.
No real RPC is dialled — provider construction is offline.
"""

from __future__ import annotations

from eth_typing import URI
from helios.runtime import build_resilient_web3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from web3 import Web3
from web3.providers.rpc import HTTPProvider


def _adapter_retry(w3: Web3) -> Retry:
    prov = w3.provider
    assert isinstance(prov, HTTPProvider)
    session = prov._request_session_manager.cache_and_return_session(URI("http://127.0.0.1:1"))
    adapter = session.get_adapter("https://example.invalid")
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    return retry


def test_returns_web3_over_http_provider() -> None:
    w3 = build_resilient_web3("http://127.0.0.1:1")
    assert isinstance(w3, Web3)
    assert isinstance(w3.provider, HTTPProvider)


def test_default_retry_policy_retries_post() -> None:
    retry = _adapter_retry(build_resilient_web3("http://127.0.0.1:1"))
    assert retry.total == 4
    assert retry.connect == 4
    assert retry.read == 4
    assert retry.status == 4
    assert retry.backoff_factor == 0.5
    # `False` => retry on every method; JSON-RPC reads + idempotent
    # raw-tx rebroadcast are POST and would otherwise be skipped.
    assert retry.allowed_methods is False
    assert set(retry.status_forcelist or ()) == {429, 500, 502, 503, 504}
    assert retry.raise_on_status is False


def test_explicit_args_override_defaults() -> None:
    retry = _adapter_retry(
        build_resilient_web3("http://127.0.0.1:1", total_retries=9, backoff_factor=1.5)
    )
    assert retry.total == 9
    assert retry.backoff_factor == 1.5


def test_env_overrides_default_but_args_win(monkeypatch) -> None:
    monkeypatch.setenv("STRATEGY_RPC_RETRIES", "11")
    monkeypatch.setenv("STRATEGY_RPC_BACKOFF", "0.75")
    env_retry = _adapter_retry(build_resilient_web3("http://127.0.0.1:1"))
    assert env_retry.total == 11
    assert env_retry.backoff_factor == 0.75

    arg_retry = _adapter_retry(build_resilient_web3("http://127.0.0.1:1", total_retries=3))
    assert arg_retry.total == 3  # explicit arg beats env


def test_malformed_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("STRATEGY_RPC_RETRIES", "not-an-int")
    retry = _adapter_retry(build_resilient_web3("http://127.0.0.1:1"))
    assert retry.total == 4
