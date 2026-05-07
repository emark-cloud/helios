"""Coingecko free-tier source. Used as fallback when Binance lacks the asset."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING

from oracle.sources.base import PriceQuote, SourceError

if TYPE_CHECKING:
    import httpx


_COINGECKO_PRICE = "https://api.coingecko.com/api/v3/simple/price"
_E18 = 10**18


class CoingeckoSource:
    """Pulls a spot price via `simple/price?ids=...&vs_currencies=usdt`."""

    name = "coingecko"

    def __init__(self, client: httpx.AsyncClient, slug_map: dict[str, tuple[str, str]]) -> None:
        # slug_map: asset_id ("KITE/USDT") -> (coingecko_id, vs_currency).
        # E.g. ("KITE/USDT", ("kite-ai", "usd")). Coingecko quotes in fiat,
        # so the chain consumer must understand "usd" ≈ "usdt" for Phase 1.
        self._client = client
        self._slugs = slug_map

    async def fetch(self, asset: str) -> PriceQuote:
        entry = self._slugs.get(asset)
        if entry is None:
            raise SourceError(f"coingecko: no slug mapping for {asset!r}")
        cg_id, vs = entry
        try:
            resp = await self._client.get(
                _COINGECKO_PRICE,
                params={"ids": cg_id, "vs_currencies": vs},
                timeout=5.0,
            )
        except Exception as exc:
            raise SourceError(f"coingecko: network error: {exc}") from exc
        if resp.status_code != 200:
            raise SourceError(f"coingecko: http {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        try:
            price = body[cg_id][vs]
        except (KeyError, TypeError) as exc:
            raise SourceError(f"coingecko: missing {cg_id}/{vs} in {body!r}") from exc
        return PriceQuote(
            asset=asset,
            price_e18=_float_to_e18(price),
            timestamp_ms=int(time.time() * 1000),
            source=self.name,
        )


def _float_to_e18(price: float | int) -> int:
    # Coingecko returns JSON numbers — route through `Decimal` so the
    # whole-number / fixed-point / scientific-notation cases all collapse
    # into one path. Phase-3 review MEDIUM: `repr(1e-05)` is `"1e-05"`
    # with no `.`, which used to fall through into `int("1e-05")` and
    # raise — common for low-priced long-tail tokens. `Decimal(str(x))`
    # via repr keeps the float-binary dust in check at the 1e-15 level.
    quantized = Decimal(repr(float(price))) * _E18
    return int(quantized.to_integral_value())
