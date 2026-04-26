"""Binance public REST source (no auth, no key)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from oracle.sources.base import PriceQuote, SourceError

if TYPE_CHECKING:
    import httpx


_BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
_E18 = 10**18


class BinanceSource:
    """Pulls latest 1-min close from `/api/v3/klines`."""

    name = "binance"

    def __init__(self, client: httpx.AsyncClient, symbol_map: dict[str, str]) -> None:
        # symbol_map maps a Helios asset id ("KITE/USDT") to the Binance symbol ("KITEUSDT").
        # If an asset isn't in the map, fetch raises SourceError (forces fallback).
        self._client = client
        self._symbols = symbol_map

    async def fetch(self, asset: str) -> PriceQuote:
        symbol = self._symbols.get(asset)
        if symbol is None:
            raise SourceError(f"binance: no symbol mapping for {asset!r}")
        try:
            resp = await self._client.get(
                _BINANCE_KLINES,
                params={"symbol": symbol, "interval": "1m", "limit": 1},
                timeout=5.0,
            )
        except Exception as exc:
            raise SourceError(f"binance: network error: {exc}") from exc
        if resp.status_code != 200:
            raise SourceError(f"binance: http {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        if not body:
            raise SourceError(f"binance: empty kline response for {symbol}")
        # Kline schema: [openTime, open, high, low, close, volume, closeTime, ...]
        kline = body[-1]
        close_str = str(kline[4])
        return PriceQuote(
            asset=asset,
            price_e18=_to_e18(close_str),
            timestamp_ms=int(time.time() * 1000),
            source=self.name,
        )


def _to_e18(decimal_str: str) -> int:
    """Convert "1234.5678" to 1234.5678 * 1e18 without floating-point loss."""
    if "." not in decimal_str:
        return int(decimal_str) * _E18
    whole, frac = decimal_str.split(".", 1)
    frac = (frac + "0" * 18)[:18]  # right-pad / truncate to 18 places
    return int(whole) * _E18 + int(frac)
