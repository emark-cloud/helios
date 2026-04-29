"""Stub yield sources advance through scripted ticks deterministically."""

from __future__ import annotations

import pytest
from oracle.sources.yield_aave_stub import AaveStubSource
from oracle.sources.yield_base import YieldSourceError
from oracle.sources.yield_compound_stub import CompoundStubSource


@pytest.mark.asyncio
async def test_aave_stub_advances_each_call() -> None:
    src = AaveStubSource()
    quotes = [(await src.fetch("aave-v3:USDC")).apy_bps_e6 for _ in range(8)]
    # 6 ticks, then holds the last value.
    assert quotes == [
        525_000_000,
        510_000_000,
        480_000_000,
        450_000_000,
        425_000_000,
        410_000_000,
        410_000_000,
        410_000_000,
    ]


@pytest.mark.asyncio
async def test_aave_stub_unknown_market_raises() -> None:
    src = AaveStubSource()
    with pytest.raises(YieldSourceError):
        await src.fetch("aave-v3:DAI")


@pytest.mark.asyncio
async def test_aave_stub_reset() -> None:
    src = AaveStubSource()
    await src.fetch("aave-v3:USDC")
    await src.fetch("aave-v3:USDC")
    src.reset()
    q = await src.fetch("aave-v3:USDC")
    assert q.apy_bps_e6 == 525_000_000


@pytest.mark.asyncio
async def test_compound_stub_diverges_from_aave() -> None:
    aave = AaveStubSource()
    compound = CompoundStubSource()
    # By tick 5 Compound USDC (530_000_000) is ~120 bps above Aave USDC
    # (425_000_000) — yield_rotation_v1 should pick the differential up.
    for _ in range(5):
        await aave.fetch("aave-v3:USDC")
        await compound.fetch("compound-v3:USDC")
    aave_apy = (await aave.fetch("aave-v3:USDC")).apy_bps_e6
    compound_apy = (await compound.fetch("compound-v3:USDC")).apy_bps_e6
    assert compound_apy - aave_apy >= 100_000_000  # ≥1.0% spread
