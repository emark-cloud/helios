"""ECDSA signer round-trip."""

from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct
from oracle.signer import LocalSigner


def test_unsigned_returns_zero_address_and_zero_sig() -> None:
    s = LocalSigner("")
    sig = s.sign_quote("KITE/USDT", price_e18=10**18, timestamp_ms=1000)
    assert s.signer_address == "0x" + "0" * 40
    assert sig.signature == b"\x00" * 65
    assert len(sig.digest) == 32


def test_signed_recovers_to_signer_address() -> None:
    pk = "0x" + "11" * 32
    s = LocalSigner(pk)
    sig = s.sign_quote("KITE/USDT", price_e18=10**18, timestamp_ms=1_700_000_000_000)
    # Recover via the same EIP-191 framing the signer uses.
    msg = encode_defunct(primitive=sig.digest)
    recovered = Account.recover_message(msg, signature=sig.signature)
    assert recovered.lower() == s.signer_address.lower()


def test_digest_is_deterministic() -> None:
    a = LocalSigner("")
    b = LocalSigner("")
    s1 = a.sign_quote("ETH/USDT", price_e18=3 * 10**21, timestamp_ms=42)
    s2 = b.sign_quote("ETH/USDT", price_e18=3 * 10**21, timestamp_ms=42)
    assert s1.digest == s2.digest
