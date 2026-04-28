"""Helios oracle service.

Phase 1: signed 1-minute price snapshots for KITE/USDT, ETH/USDT.
Sources are tried in declaration order — Binance → Coingecko → (Algebra
in Phase 2). When `SCENARIO_MODE=1`, all live sources are bypassed and
the scenario JSON drives the price series.

The on-chain root anchor (5-min cadence to a future `OraclePriceAnchor`)
is deferred to Phase 2 — we expose the in-memory chain root via
`GET /v1/snapshots/root` so the anchor task / strategies can read it.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from oracle.poller import Poller
from oracle.signer import LocalSigner
from oracle.sources.base import PriceSource
from oracle.sources.binance import BinanceSource
from oracle.sources.coingecko import CoingeckoSource
from oracle.sources.scenario import ScenarioSource
from oracle.state import SnapshotStore


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="ORACLE_", env_file=".env", extra="ignore")

    bar_interval_sec: int = 60
    signer_pk: str = Field(default="", validation_alias="ORACLE_SIGNER_PK")
    # Comma-separated, e.g. "KITE/USDT,ETH/USDT".
    assets: str = Field(default="KITE/USDT,ETH/USDT", validation_alias="ORACLE_ASSETS")
    snapshot_capacity: int = 1024
    http_port: int = 8003


# Default symbol mappings. Override at process boundary if Binance / Coingecko
# add or rename listings.
_BINANCE_SYMBOLS: dict[str, str] = {
    "ETH/USDT": "ETHUSDT",
    "BTC/USDT": "BTCUSDT",
    # KITE intentionally omitted — Binance has no KITE/USDT pair as of
    # 2026-04-25, so the Coingecko fallback handles it.
}
_COINGECKO_SLUGS: dict[str, tuple[str, str]] = {
    "KITE/USDT": ("kite-ai", "usd"),
    "ETH/USDT": ("ethereum", "usd"),
    "BTC/USDT": ("bitcoin", "usd"),
}


def _parse_assets(raw: str) -> list[str]:
    return [a.strip() for a in raw.split(",") if a.strip()]


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]
    assets = _parse_assets(cfg.assets)
    signer = LocalSigner(cfg.signer_pk)
    store = SnapshotStore(signer=signer, capacity_per_asset=cfg.snapshot_capacity)

    http_client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "helios-oracle/0.1"})
    sources: list[PriceSource] = []
    if cfg.scenario_mode:
        sources.append(ScenarioSource(cfg.scenario_file))
    else:
        sources.append(BinanceSource(http_client, _BINANCE_SYMBOLS))
        sources.append(CoingeckoSource(http_client, _COINGECKO_SLUGS))

    poller = Poller(store=store, sources=sources, assets=assets, interval_sec=cfg.bar_interval_sec)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        poller.start()
        try:
            yield
        finally:
            await poller.stop()
            await http_client.aclose()

    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, str | int | list[str]]:
        return {
            "service": "oracle",
            "bar_interval_sec": cfg.bar_interval_sec,
            "scenario_mode": int(cfg.scenario_mode),
            "signer": signer.signer_address,
            "assets": assets,
            "sources": [s.name for s in sources],
        }

    @router.get("/snapshots/recent")
    async def recent(
        asset: str = Query(...),
        n: int = Query(default=16, ge=1, le=512),
    ) -> dict[str, object]:
        if asset not in assets:
            raise HTTPException(status_code=404, detail=f"asset not tracked: {asset}")
        snaps = store.recent(asset, n)
        return {
            "asset": asset,
            "n": len(snaps),
            "signer": signer.signer_address,
            "snapshots": [
                {
                    "asset": s.asset,
                    "price_e18": str(s.price_e18),
                    "timestamp_ms": s.timestamp_ms,
                    "source": s.source,
                    "digest": _hex(s.digest),
                    "signature": _hex(s.signature),
                }
                for s in snaps
            ],
        }

    @router.get("/snapshots/root")
    async def root_endpoint(
        asset: str = Query(...),
        n: int = Query(default=16, ge=1, le=512),
    ) -> dict[str, object]:
        if asset not in assets:
            raise HTTPException(status_code=404, detail=f"asset not tracked: {asset}")
        chain_root = store.chain_root(asset, n)
        head_ts = store.head_timestamp_ms(asset)
        return {
            "asset": asset,
            "n": n,
            "root": _hex(chain_root),
            "head_timestamp_ms": head_ts,
            "signer": signer.signer_address,
            "hash": "keccak256",
        }

    app = create_app(name="oracle", settings=cfg, routers=[router])
    # `create_app` builds its own lifespan around DB; we layer the poller's lifespan
    # by wrapping the app's existing one.
    app.router.lifespan_context = _compose_lifespans(app.router.lifespan_context, lifespan)
    # Surface helpers for tests.
    app.state.store = store  # type: ignore[attr-defined]
    app.state.poller = poller  # type: ignore[attr-defined]
    app.state.signer = signer  # type: ignore[attr-defined]
    return app


def _compose_lifespans(outer, inner):
    """Run two lifespan context managers nested: outer → inner → yield."""

    @asynccontextmanager
    async def composed(app: FastAPI) -> AsyncIterator[None]:
        async with outer(app), inner(app):
            yield

    return composed


def load_scenario(path: str) -> dict[str, object]:
    """Helper for tests / tooling — read a scenario JSON file."""
    with open(path) as fh:
        return json.load(fh)
