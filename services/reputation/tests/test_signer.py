"""EIP-712 sign + recover round-trip.

Mirrors the typehash + domain in `contracts/src/ReputationAnchor.sol`.
"""

from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_typed_data
from reputation.signer import (
    _DOMAIN_NAME,
    _DOMAIN_VERSION,
    _TYPES,
    ActorType,
    ReputationSigner,
    ReputationUpdate,
)

_PK = "0x" + "11" * 32
_ANCHOR = "0x" + "ab" * 20
_CHAIN_ID = 2368


def _make_update() -> ReputationUpdate:
    return ReputationUpdate(
        actor="0x" + "cd" * 20,
        actor_type=ActorType.STRATEGY,
        current_score=4200,
        last_update_block=1_700_000_000,
        total_attested_trades=17,
        total_realized_pnl=10**19,
        max_drawdown_bps=350,
        proof_validity_rate_bps=10_000,
    )


def test_unsigned_returns_zero_signature() -> None:
    signer = ReputationSigner("", _CHAIN_ID, _ANCHOR)
    signed = signer.sign_update(_make_update())
    assert signed.signature == b"\x00" * 65
    assert signed.signer == "0x" + "0" * 40


def test_signature_recovers_to_signer_address() -> None:
    signer = ReputationSigner(_PK, _CHAIN_ID, _ANCHOR)
    update = _make_update()
    signed = signer.sign_update(update)

    domain = {
        "name": _DOMAIN_NAME,
        "version": _DOMAIN_VERSION,
        "chainId": _CHAIN_ID,
        "verifyingContract": _ANCHOR,
    }
    message = {
        "actor": update.actor,
        "actorType": int(update.actor_type),
        "currentScore": update.current_score,
        "lastUpdateBlock": update.last_update_block,
        "totalAttestedTrades": update.total_attested_trades,
        "totalRealizedPnL": update.total_realized_pnl,
        "maxDrawdownBps": update.max_drawdown_bps,
        "proofValidityRateBps": update.proof_validity_rate_bps,
    }
    encoded = encode_typed_data(domain_data=domain, message_types=_TYPES, message_data=message)
    recovered = Account.recover_message(encoded, signature=signed.signature)
    assert recovered.lower() == signer.signer_address.lower()


def test_score_change_changes_signature() -> None:
    signer = ReputationSigner(_PK, _CHAIN_ID, _ANCHOR)
    a = signer.sign_update(_make_update())
    b_update = ReputationUpdate(
        actor=a.update.actor,
        actor_type=a.update.actor_type,
        current_score=a.update.current_score + 1,
        last_update_block=a.update.last_update_block,
        total_attested_trades=a.update.total_attested_trades,
        total_realized_pnl=a.update.total_realized_pnl,
        max_drawdown_bps=a.update.max_drawdown_bps,
        proof_validity_rate_bps=a.update.proof_validity_rate_bps,
    )
    b = signer.sign_update(b_update)
    assert a.signature != b.signature
