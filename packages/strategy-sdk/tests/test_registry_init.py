"""Idempotent commitInitialParamsHash helper — three-branch coverage.

The helper is a one-shot called from each strategy's FastAPI lifespan
on container start. The three branches are:
    1. on-chain hash is zero → broadcast commit, `committed_now=True`
    2. on-chain hash matches → no-op, `committed_now=False`
    3. on-chain hash differs → raise `ParamsHashMismatchError` (fatal)

Mocking web3 keeps the test purely deterministic — `_send`-style anvil
fixtures live in scripts/ and would tie strategy-sdk tests to the rest
of the workspace. The helper's contract is narrow enough that a mock
of `paramsHashOf` + `commitInitialParamsHash` covers it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from helios.runtime import (
    CommitOutcome,
    ParamsHashMismatchError,
    ensure_params_committed,
)

# Synthetic 32-byte hashes for the three branches.
_HASH_A = b"\xaa" * 32
_HASH_B = b"\xbb" * 32
_ZERO = b"\x00" * 32

# Fake chain id + addresses; the helper never broadcasts in tests
# because `eth.send_raw_transaction` is mocked to return a stub hash.
_REGISTRY = "0x" + "11" * 20
_VAULT = "0x" + "22" * 20
_OPERATOR_PK = "0x" + "01" * 32  # anvil-style deterministic key


def _make_w3(*, on_chain_hash: bytes, gas_price: int = 1_000_000) -> MagicMock:
    """Build a mock Web3 surface that returns the configured `paramsHashOf`
    response and otherwise behaves like a no-op chain (always-success
    receipt, monotone nonce). Mirrors `web3.eth` enough that the helper
    runs end-to-end."""
    w3 = MagicMock()
    w3.eth.chain_id = 31337
    w3.eth.gas_price = gas_price
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.send_raw_transaction.return_value = b"\xde" * 32
    w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}

    # Address checksumming is real — the helper passes vault/registry
    # through `Web3.to_checksum_address`, which is a static utility on
    # the real web3 module. Patch the import path: the mock's
    # `to_checksum_address` is shadowed by the class method on real Web3
    # at module import time, so we just let the real call go through.
    contract = MagicMock()
    contract.functions.paramsHashOf.return_value.call.return_value = on_chain_hash
    contract.functions.commitInitialParamsHash.return_value.build_transaction.return_value = {
        "from": "0x" + "0" * 40,
        "nonce": 0,
        "gas": 200_000,
        "gasPrice": gas_price,
        "chainId": 31337,
        "to": _REGISTRY,
        "data": "0x",
    }
    w3.eth.contract.return_value = contract
    return w3


def test_commits_when_registry_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    w3 = _make_w3(on_chain_hash=_ZERO)
    # Stub the `Account.from_key` + `sign_transaction` plumbing so we
    # don't need a real eth-account install; the helper uses these
    # signatures opaquely.
    fake_account = MagicMock()
    fake_account.address = "0x" + "ab" * 20
    fake_account.sign_transaction.return_value = MagicMock(raw_transaction=b"\x00" * 8)
    monkeypatch.setattr(
        "helios.runtime.registry_init.Account.from_key",
        lambda _pk: fake_account,
    )

    out = ensure_params_committed(
        w3=w3,
        registry_address=_REGISTRY,
        vault_address=_VAULT,
        params_hash=_HASH_A,
        operator_pk=_OPERATOR_PK,
    )
    assert isinstance(out, CommitOutcome)
    assert out.committed_now is True
    assert out.params_hash == _HASH_A
    assert out.tx_hash is not None
    # The send path went through.
    w3.eth.send_raw_transaction.assert_called_once()


def test_noop_when_registry_already_matches() -> None:
    w3 = _make_w3(on_chain_hash=_HASH_A)
    out = ensure_params_committed(
        w3=w3,
        registry_address=_REGISTRY,
        vault_address=_VAULT,
        params_hash=_HASH_A,
        operator_pk=_OPERATOR_PK,
    )
    assert out.committed_now is False
    assert out.tx_hash is None
    # No tx broadcast on the no-op branch.
    w3.eth.send_raw_transaction.assert_not_called()


def test_raises_on_mismatch() -> None:
    """Mismatched on-chain hash is fatal — `commitInitialParamsHash` is
    one-shot per vault on the registry, so a wrong hash means the
    operator must redeploy. The runtime treats this as a hard fail
    rather than silently continuing to sign proofs the verifier will
    reject."""
    w3 = _make_w3(on_chain_hash=_HASH_B)
    with pytest.raises(ParamsHashMismatchError) as excinfo:
        ensure_params_committed(
            w3=w3,
            registry_address=_REGISTRY,
            vault_address=_VAULT,
            params_hash=_HASH_A,
            operator_pk=_OPERATOR_PK,
        )
    err = excinfo.value
    assert err.on_chain == _HASH_B
    assert err.computed == _HASH_A
    # Address comes back checksummed.
    assert err.vault.startswith("0x")
    assert err.vault.lower() == _VAULT.lower()
    # No commit attempted on the mismatch branch.
    w3.eth.send_raw_transaction.assert_not_called()


def test_rejects_short_hash() -> None:
    """params_hash must be exactly 32 bytes — common operator footgun
    is passing the int form. Catch it at the boundary so the runtime
    crashes loudly instead of writing 0x00 padding to chain."""
    w3 = _make_w3(on_chain_hash=_ZERO)
    with pytest.raises(ValueError, match="must be 32 bytes"):
        ensure_params_committed(
            w3=w3,
            registry_address=_REGISTRY,
            vault_address=_VAULT,
            params_hash=b"\x01" * 31,
            operator_pk=_OPERATOR_PK,
        )
