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

from oracle.anchor import (
    AnchorPoster,
    MultiChainAnchorPoster,
    PriceAnchorScheduler,
    YieldAnchorScheduler,
)
from oracle.poller import Poller, YieldPoller
from oracle.signer import LocalSigner
from oracle.sources.base import PriceSource
from oracle.sources.binance import BinanceSource
from oracle.sources.coingecko import CoingeckoSource
from oracle.sources.scenario import ScenarioSource
from oracle.sources.yield_aave_stub import AaveStubSource
from oracle.sources.yield_base import YieldSource
from oracle.sources.yield_compound_stub import CompoundStubSource
from oracle.state import SnapshotStore
from oracle.yield_state import YieldStore


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="ORACLE_", env_file=".env", extra="ignore")

    bar_interval_sec: int = 60
    signer_pk: str = Field(default="", validation_alias="ORACLE_SIGNER_PK")
    # Comma-separated, e.g. "KITE/USDT,ETH/USDT".
    assets: str = Field(default="KITE/USDT,ETH/USDT", validation_alias="ORACLE_ASSETS")
    snapshot_capacity: int = 1024
    http_port: int = 8003

    # Yield oracle — Phase 2. Comma-separated `(source:market_pair)` ids,
    # e.g. "aave-v3:USDC,aave-v3:USDT,compound-v3:USDC,compound-v3:USDT".
    yield_markets: str = Field(
        default="aave-v3:USDC,aave-v3:USDT,compound-v3:USDC,compound-v3:USDT",
        validation_alias="ORACLE_YIELD_MARKETS",
    )
    yield_interval_sec: int = Field(default=60, validation_alias="ORACLE_YIELD_INTERVAL_SEC")
    yield_capacity: int = Field(default=512, validation_alias="ORACLE_YIELD_CAPACITY")

    # Phase 2 anchor wiring. All optional — empty values keep the poster
    # in dry-run mode (records pending commits for tests, doesn't submit).
    rpc_url: str = Field(default="", validation_alias="KITE_RPC_URL")
    chain_id: int = Field(default=2368, validation_alias="ORACLE_CHAIN_ID")
    price_anchor_address: str = Field(default="", validation_alias="ORACLE_PRICE_ANCHOR_ADDRESS")
    yield_anchor_address: str = Field(default="", validation_alias="ORACLE_YIELD_ANCHOR_ADDRESS")
    anchor_interval_bars: int = Field(default=50, validation_alias="ORACLE_ANCHOR_INTERVAL_BARS")
    anchor_chain_depth: int = Field(default=16, validation_alias="ORACLE_ANCHOR_CHAIN_DEPTH")

    # Phase 5 cross-chain replication. Each mirror chain is fully
    # optional — leaving the RPC blank disables replication for that
    # chain. The same `ORACLE_SIGNER_PK` signs all chains; only the
    # EIP-712 domain (chainId + verifyingContract) differs per mirror.
    base_sepolia_rpc_url: str = Field(default="", validation_alias="ORACLE_BASE_SEPOLIA_RPC")
    base_sepolia_chain_id: int = Field(
        default=84_532, validation_alias="ORACLE_BASE_SEPOLIA_CHAIN_ID"
    )
    base_sepolia_price_anchor: str = Field(
        default="", validation_alias="ORACLE_BASE_SEPOLIA_PRICE_ANCHOR"
    )
    base_sepolia_yield_anchor: str = Field(
        default="", validation_alias="ORACLE_BASE_SEPOLIA_YIELD_ANCHOR"
    )

    arbitrum_sepolia_rpc_url: str = Field(
        default="", validation_alias="ORACLE_ARBITRUM_SEPOLIA_RPC"
    )
    arbitrum_sepolia_chain_id: int = Field(
        default=421_614, validation_alias="ORACLE_ARBITRUM_SEPOLIA_CHAIN_ID"
    )
    arbitrum_sepolia_price_anchor: str = Field(
        default="", validation_alias="ORACLE_ARBITRUM_SEPOLIA_PRICE_ANCHOR"
    )
    arbitrum_sepolia_yield_anchor: str = Field(
        default="", validation_alias="ORACLE_ARBITRUM_SEPOLIA_YIELD_ANCHOR"
    )


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


def _build_mirror_posters(cfg: Settings, kind: str) -> list[AnchorPoster]:
    """Build the optional per-chain mirror posters. A chain is enabled
    when its RPC URL *and* the per-kind anchor address are both set;
    half-configured chains are skipped silently so a partial deploy
    can't accidentally start submitting to nowhere.
    """
    mirrors: list[AnchorPoster] = []
    chains: list[tuple[str, str, int, str]] = [
        (
            "base-sepolia",
            cfg.base_sepolia_rpc_url,
            cfg.base_sepolia_chain_id,
            cfg.base_sepolia_price_anchor if kind == "price" else cfg.base_sepolia_yield_anchor,
        ),
        (
            "arbitrum-sepolia",
            cfg.arbitrum_sepolia_rpc_url,
            cfg.arbitrum_sepolia_chain_id,
            cfg.arbitrum_sepolia_price_anchor
            if kind == "price"
            else cfg.arbitrum_sepolia_yield_anchor,
        ),
    ]
    for _label, rpc, cid, addr in chains:
        if not rpc or not addr:
            continue
        mirrors.append(
            AnchorPoster(
                kind=kind,  # type: ignore[arg-type]
                rpc_url=rpc,
                signer_pk=cfg.signer_pk,
                anchor_address=addr,
                chain_id=cid,
            )
        )
    return mirrors


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]
    assets = _parse_assets(cfg.assets)
    yield_markets = _parse_assets(cfg.yield_markets)
    signer = LocalSigner(cfg.signer_pk)
    store = SnapshotStore(signer=signer, capacity_per_asset=cfg.snapshot_capacity)
    yield_store = YieldStore(signer=signer, capacity_per_market=cfg.yield_capacity)

    http_client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "helios-oracle/0.1"})
    sources: list[PriceSource] = []
    if cfg.scenario_mode:
        sources.append(ScenarioSource(cfg.scenario_file))
    else:
        sources.append(BinanceSource(http_client, _BINANCE_SYMBOLS))
        sources.append(CoingeckoSource(http_client, _COINGECKO_SLUGS))

    # Yield sources — Phase 2 ships the two stub feeders. Real Aave +
    # Compound integrations land in Phase 5.
    yield_sources: list[YieldSource] = [AaveStubSource(), CompoundStubSource()]

    price_canonical = AnchorPoster(
        kind="price",
        rpc_url=cfg.rpc_url,
        signer_pk=cfg.signer_pk,
        anchor_address=cfg.price_anchor_address,
        chain_id=cfg.chain_id,
    )
    yield_canonical = AnchorPoster(
        kind="yield",
        rpc_url=cfg.rpc_url,
        signer_pk=cfg.signer_pk,
        anchor_address=cfg.yield_anchor_address,
        chain_id=cfg.chain_id,
    )
    price_mirrors = _build_mirror_posters(cfg, "price")
    yield_mirrors = _build_mirror_posters(cfg, "yield")
    price_poster = MultiChainAnchorPoster(canonical=price_canonical, mirrors=price_mirrors)
    yield_poster = MultiChainAnchorPoster(canonical=yield_canonical, mirrors=yield_mirrors)

    price_scheduler = PriceAnchorScheduler(
        store=store,
        poster=price_poster,  # type: ignore[arg-type]
        interval_bars=cfg.anchor_interval_bars,
        chain_depth=cfg.anchor_chain_depth,
    )
    yield_scheduler = YieldAnchorScheduler(
        store=yield_store,
        poster=yield_poster,  # type: ignore[arg-type]
        interval_bars=cfg.anchor_interval_bars,
        chain_depth=cfg.anchor_chain_depth,
    )
    # Use the async hook variants in production: the underlying Web3
    # `wait_for_transaction_receipt` blocks up to `_RECEIPT_TIMEOUT_SEC`,
    # so a sync hook would freeze the event loop (Poller, FastAPI WS
    # clients) every commit window.
    poller = Poller(
        store=store,
        sources=sources,
        assets=assets,
        interval_sec=cfg.bar_interval_sec,
        on_snapshot=price_scheduler.on_bar_async,
    )
    yield_poller = YieldPoller(
        store=yield_store,
        sources=yield_sources,
        markets=yield_markets,
        interval_sec=cfg.yield_interval_sec,
        on_snapshot=yield_scheduler.on_bar_async,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        poller.start()
        yield_poller.start()
        try:
            yield
        finally:
            await yield_poller.stop()
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
        # Poseidon root is a BN254 field element. Serialize as decimal
        # string (canonical for circuits) and as 32-byte hex (canonical
        # for `OraclePriceAnchor.commit(bytes32, ...)`).
        chain_root = store.chain_root(asset, n)
        head_ts = store.head_timestamp_ms(asset)
        return {
            "asset": asset,
            "n": n,
            "root": str(chain_root),
            "root_bytes32": "0x" + chain_root.to_bytes(32, "big").hex(),
            "head_timestamp_ms": head_ts,
            "signer": signer.signer_address,
            "hash": "poseidon",
        }

    @router.get("/yield/markets")
    async def yield_markets_endpoint() -> dict[str, object]:
        return {
            "configured": yield_markets,
            "active": yield_store.markets(),
            "signer": signer.signer_address,
        }

    @router.get("/yield/recent")
    async def yield_recent(
        market_id: str = Query(...),
        n: int = Query(default=16, ge=1, le=512),
    ) -> dict[str, object]:
        if market_id not in yield_markets:
            raise HTTPException(status_code=404, detail=f"market not tracked: {market_id}")
        snaps = yield_store.recent(market_id, n)
        return {
            "market_id": market_id,
            "n": len(snaps),
            "signer": signer.signer_address,
            "snapshots": [
                {
                    "market_id": s.market_id,
                    "apy_bps_e6": str(s.apy_bps_e6),
                    "timestamp_ms": s.timestamp_ms,
                    "source": s.source,
                    "digest": _hex(s.digest),
                    "signature": _hex(s.signature),
                }
                for s in snaps
            ],
        }

    @router.get("/yield/root")
    async def yield_root(
        market_id: str = Query(...),
        n: int = Query(default=16, ge=1, le=512),
    ) -> dict[str, object]:
        if market_id not in yield_markets:
            raise HTTPException(status_code=404, detail=f"market not tracked: {market_id}")
        chain_root = yield_store.chain_root(market_id, n)
        head_ts = yield_store.head_timestamp_ms(market_id)
        return {
            "market_id": market_id,
            "n": n,
            "root": str(chain_root),
            "root_bytes32": "0x" + chain_root.to_bytes(32, "big").hex(),
            "head_timestamp_ms": head_ts,
            "signer": signer.signer_address,
            "hash": "poseidon",
        }

    app = create_app(name="oracle", settings=cfg, routers=[router])
    # `create_app` builds its own lifespan around DB; we layer the poller's lifespan
    # by wrapping the app's existing one.
    app.router.lifespan_context = _compose_lifespans(app.router.lifespan_context, lifespan)
    # Surface helpers for tests.
    app.state.store = store  # type: ignore[attr-defined]
    app.state.yield_store = yield_store  # type: ignore[attr-defined]
    app.state.poller = poller  # type: ignore[attr-defined]
    app.state.yield_poller = yield_poller  # type: ignore[attr-defined]
    app.state.signer = signer  # type: ignore[attr-defined]
    app.state.price_anchor_poster = price_poster  # type: ignore[attr-defined]
    app.state.price_anchor_scheduler = price_scheduler  # type: ignore[attr-defined]
    app.state.yield_anchor_poster = yield_poster  # type: ignore[attr-defined]
    app.state.yield_anchor_scheduler = yield_scheduler  # type: ignore[attr-defined]
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
