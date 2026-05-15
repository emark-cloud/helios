"""`seed_strategy_capital` / `read_erc20_balance` — cash seed vs the
position-aware NAV opt-out.

The seed always sets spendable base cash (`available_capital` + the
exact wei balance for the `amount_in` clamp). It also sets `nav` to that
cash *only* when `set_nav=True`. A runtime that values held non-base
positions itself passes `set_nav=False` so a vault that has swapped its
base leg into other assets does not report NAV ≈ 0.
"""

from __future__ import annotations

from typing import Any

from helios.runtime.nav_seed import read_erc20_balance, seed_strategy_capital


class _FakeBalanceFn:
    def __init__(self, amount: int) -> None:
        self._amount = amount

    def call(self) -> int:
        return self._amount


class _FakeContract:
    def __init__(self, amount: int) -> None:
        self.functions = self
        self._amount = amount

    def balanceOf(self, _holder: str) -> _FakeBalanceFn:  # ERC20 ABI name
        return _FakeBalanceFn(self._amount)


class _FakeEth:
    def __init__(self, amount: int) -> None:
        self._amount = amount

    def contract(self, *, address: str, abi: Any) -> _FakeContract:
        del address, abi
        return _FakeContract(self._amount)


class _FakeW3:
    def __init__(self, amount: int) -> None:
        self.eth = _FakeEth(amount)

    @staticmethod
    def to_checksum_address(addr: str) -> str:
        return addr


class _RecordingStrategy:
    def __init__(self) -> None:
        self.capital: float | None = None
        self.nav: float | None = None
        self.wei: int | None = None

    def _set_capital(self, usd: float) -> None:
        self.capital = usd

    def _set_nav(self, usd: float) -> None:
        self.nav = usd

    def _set_base_asset_balance_wei(self, wei: int) -> None:
        self.wei = wei


def test_read_erc20_balance_zero_on_falsy_inputs() -> None:
    assert read_erc20_balance(w3=None, token_address="0xabc", holder_address="0xdef") == 0
    assert read_erc20_balance(w3=_FakeW3(5), token_address="", holder_address="0xdef") == 0
    assert read_erc20_balance(w3=_FakeW3(5), token_address="0xabc", holder_address="") == 0


def test_read_erc20_balance_returns_raw() -> None:
    w3 = _FakeW3(123_456)
    assert read_erc20_balance(w3=w3, token_address="0xabc", holder_address="0xdef") == 123_456


def test_seed_sets_cash_and_nav_by_default() -> None:
    s = _RecordingStrategy()
    # 5 mUSDC at 18 decimals.
    seeded = seed_strategy_capital(
        strategy=s,
        w3=_FakeW3(5 * 10**18),
        base_asset_address="0xUSDC",
        vault_address="0xVAULT",
        base_asset_decimals=18,
    )
    assert seeded == 5.0
    assert s.capital == 5.0
    assert s.nav == 5.0  # default set_nav=True mirrors cash
    assert s.wei == 5 * 10**18


def test_seed_set_nav_false_leaves_nav_untouched() -> None:
    """A position-aware runtime owns NAV: the seed must set cash + the
    exact wei (the `amount_in` clamp) but never touch `nav`, so a vault
    drained into non-base assets isn't reported as NAV ≈ 0."""
    s = _RecordingStrategy()
    s.nav = 4_200.0  # pretend the runtime already marked positions to market
    seeded = seed_strategy_capital(
        strategy=s,
        w3=_FakeW3(0),  # base leg fully swapped out → 0 cash
        base_asset_address="0xUSDC",
        vault_address="0xVAULT",
        base_asset_decimals=18,
        set_nav=False,
    )
    assert seeded == 0.0
    assert s.capital == 0.0
    assert s.wei == 0
    assert s.nav == 4_200.0  # untouched — runtime keeps the MTM value


def test_seed_respects_base_asset_decimals() -> None:
    s = _RecordingStrategy()
    # 1_000_000 raw at 6 decimals == 1.0 mUSDC (Base/Arb scale).
    seeded = seed_strategy_capital(
        strategy=s,
        w3=_FakeW3(1_000_000),
        base_asset_address="0xUSDC",
        vault_address="0xVAULT",
        base_asset_decimals=6,
    )
    assert seeded == 1.0
    assert s.capital == 1.0
