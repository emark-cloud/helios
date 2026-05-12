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
from oracle.commit_mirror import CommitMirror
from oracle.poller import Poller, YieldPoller
from oracle.router_mirror import PairSpec, RouterPriceMirror
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
    # Comma-separated, e.g. "KITE/USDT,ETH/USDT". Phase-6 real-P&L bumps
    # the default to cover the new test universe (mWBTC, mWETH, mSOL).
    assets: str = Field(
        default="KITE/USDT,BTC/USDT,ETH/USDT,SOL/USDT",
        validation_alias="ORACLE_ASSETS",
    )
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

    # Phase-6 real-P&L: mirror oracle prices into MockSwapRouter.setPrice
    # so on-chain swaps execute at live mid (with bps spread). All optional
    # — leave any field blank to keep the keeper in dry-run mode (records
    # pending updates without submitting), same gating as AnchorPoster.
    router_mirror_enabled: bool = Field(default=False, validation_alias="ROUTER_MIRROR_ENABLED")
    router_mirror_address: str = Field(default="", validation_alias="ROUTER_MIRROR_ADDRESS")
    router_mirror_signer_pk: str = Field(default="", validation_alias="ROUTER_MIRROR_SIGNER_PK")
    router_mirror_spread_bps: int = Field(default=5, validation_alias="ROUTER_MIRROR_SPREAD_BPS")
    router_mirror_token_usdc: str = Field(default="", validation_alias="ROUTER_MIRROR_TOKEN_USDC")
    router_mirror_token_wbtc: str = Field(default="", validation_alias="ROUTER_MIRROR_TOKEN_WBTC")
    router_mirror_token_weth: str = Field(default="", validation_alias="ROUTER_MIRROR_TOKEN_WETH")
    router_mirror_token_wsol: str = Field(default="", validation_alias="ROUTER_MIRROR_TOKEN_WSOL")
    # USDC has 6 decimals on Kite testnet (mUSDC); the new universe assets
    # use realistic decimals (WBTC=8, WETH=18, SOL=9). Override per-asset
    # if a redeploy ever changes a token's decimals.
    router_mirror_usdc_decimals: int = Field(
        default=6, validation_alias="ROUTER_MIRROR_USDC_DECIMALS"
    )
    router_mirror_wbtc_decimals: int = Field(
        default=8, validation_alias="ROUTER_MIRROR_WBTC_DECIMALS"
    )
    router_mirror_weth_decimals: int = Field(
        default=18, validation_alias="ROUTER_MIRROR_WETH_DECIMALS"
    )
    router_mirror_wsol_decimals: int = Field(
        default=9, validation_alias="ROUTER_MIRROR_WSOL_DECIMALS"
    )


# Default symbol mappings. Override at process boundary if Binance / Coingecko
# add or rename listings.
_BINANCE_SYMBOLS: dict[str, str] = {
    "ETH/USDT": "ETHUSDT",
    "BTC/USDT": "BTCUSDT",
    # WETH alias — the reference momentum_v1 strategy queries oracle by
    # the same symbol it lists in its `asset_universe`. Binance reports
    # ETH and WETH at the same price; treat the alias as ETH.
    "WETH": "ETHUSDT",
    # KITE intentionally omitted from Binance map — no KITE/USDT pair as
    # of 2026-04-25, Coingecko fallback below handles both KITE/USDT and
    # the WKITE alias the reference strategies use.
}
_COINGECKO_SLUGS: dict[str, tuple[str, str]] = {
    # `kite-ai` was the early-2026 placeholder; Kite mainnet launched
    # 2026-04-28 and Coingecko relisted the token under `kite-2` (rank
    # 128 as of 2026-05-09). The old slug now 404s ("coin not found").
    "KITE/USDT": ("kite-2", "usd"),
    "WKITE": ("kite-2", "usd"),
    "ETH/USDT": ("ethereum", "usd"),
    "WETH": ("ethereum", "usd"),
    "BTC/USDT": ("bitcoin", "usd"),
    # Phase-6 real-P&L: SOL/USDT added so the new mSOL leg of the test
    # universe gets a Coingecko fallback when Binance throttles.
    "SOL/USDT": ("solana", "usd"),
}


# Reference strategies (`momentum_v1`, `mean_reversion_v1`) declare their
# `asset_universe` in token-symbol form (`WBTC`, `WETH`, `WSOL`) so the
# operator-facing API stays in vault token names. The live oracle keys
# its snapshot rings by exchange-pair names (`BTC/USDT`, `ETH/USDT`,
# `SOL/USDT`) because those are what Binance + Coingecko index. Without
# a translation, every strategy fetch returns 404 ("asset not tracked")
# and no witness ever builds. Resolve at the route layer so the snapshot
# store stays single-keyed and aliases never bifurcate state.
_ALIASES: dict[str, str] = {
    "WBTC": "BTC/USDT",
    "WETH": "ETH/USDT",
    "WSOL": "SOL/USDT",
}


def _resolve_asset(asset: str) -> str:
    return _ALIASES.get(asset, asset)


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

    # CommitMirror snaps the committed window so HTTP `/snapshots/recent`
    # and `/snapshots/root` serve exactly what the on-chain anchor saw —
    # otherwise strategies fetching the live ring race the next commit
    # and submit a root the anchor never signed (UnknownOracleRoot
    # revert on `executeWithProof`).
    commit_mirror = CommitMirror()
    price_scheduler = PriceAnchorScheduler(
        store=store,
        poster=price_poster,  # type: ignore[arg-type]
        interval_bars=cfg.anchor_interval_bars,
        chain_depth=cfg.anchor_chain_depth,
        mirror=commit_mirror,
    )
    yield_scheduler = YieldAnchorScheduler(
        store=yield_store,
        poster=yield_poster,  # type: ignore[arg-type]
        interval_bars=cfg.anchor_interval_bars,
        chain_depth=cfg.anchor_chain_depth,
    )
    # Phase-6 real-P&L: build the optional MockSwapRouter price mirror.
    # The mirror is gated on `router_mirror_enabled`; tokens with empty
    # addresses are skipped so a half-configured deploy can't half-update
    # router prices.
    router_mirror = _build_router_mirror(cfg, store)

    # Use the async hook variants in production: the underlying Web3
    # `wait_for_transaction_receipt` blocks up to `_RECEIPT_TIMEOUT_SEC`,
    # so a sync hook would freeze the event loop (Poller, FastAPI WS
    # clients) every commit window.
    on_snapshot = _compose_on_snapshot(price_scheduler, router_mirror)
    poller = Poller(
        store=store,
        sources=sources,
        assets=assets,
        interval_sec=cfg.bar_interval_sec,
        on_snapshot=on_snapshot,
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
        asset = _resolve_asset(asset)
        if asset not in assets:
            raise HTTPException(status_code=404, detail=f"asset not tracked: {asset}")
        # Prefer the committed mirror so strategies fetch a window the
        # on-chain anchor has actually signed. Live-ring fallback covers
        # cold start before any commit has landed for the asset.
        committed = commit_mirror.get(asset)
        if committed is not None and len(committed.snapshots) >= n:
            snaps = committed.snapshots[:n]
            source_view = "committed"
        else:
            snaps = store.recent(asset, n)
            source_view = "live"
        return {
            "asset": asset,
            "n": len(snaps),
            "signer": signer.signer_address,
            "view": source_view,
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
        asset = _resolve_asset(asset)
        if asset not in assets:
            raise HTTPException(status_code=404, detail=f"asset not tracked: {asset}")
        # Poseidon root is a BN254 field element. Serialize as decimal
        # string (canonical for circuits) and as 32-byte hex (canonical
        # for `OraclePriceAnchor.commit(bytes32, ...)`).
        # Prefer the most-recent committed root over the live-ring
        # recomputation so the strategy sees a root the on-chain anchor
        # has actually accepted. Mirror only serves when its chain depth
        # is ≥ the requested `n`; otherwise fall back to live-ring
        # computation (cold-start, mismatched depths during a config
        # transition).
        committed = commit_mirror.get(asset)
        if committed is not None and len(committed.snapshots) >= n:
            chain_root = committed.root
            head_ts: int | None = committed.window_end_ms
            source_view = "committed"
        else:
            chain_root = store.chain_root(asset, n)
            head_ts = store.head_timestamp_ms(asset)
            source_view = "live"
        return {
            "asset": asset,
            "n": n,
            "root": str(chain_root),
            "root_bytes32": "0x" + chain_root.to_bytes(32, "big").hex(),
            "head_timestamp_ms": head_ts,
            "signer": signer.signer_address,
            "hash": "poseidon",
            "view": source_view,
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
    app.state.router_mirror = router_mirror  # type: ignore[attr-defined]
    app.state.commit_mirror = commit_mirror  # type: ignore[attr-defined]
    return app


def _build_router_mirror(cfg: Settings, store: SnapshotStore) -> RouterPriceMirror | None:
    """Construct the optional `RouterPriceMirror` from settings.

    Returns None when the keeper is disabled, USDC isn't configured, or
    no asset legs are configured — any of those means there's nothing
    sensible to mirror, and we should leave the Poller's on_snapshot
    callback alone.
    """
    if not cfg.router_mirror_enabled or not cfg.router_mirror_token_usdc:
        return None

    asset_legs: list[tuple[str, str, str, int]] = []
    if cfg.router_mirror_token_wbtc:
        asset_legs.append(
            ("BTC/USDT", "WBTC", cfg.router_mirror_token_wbtc, cfg.router_mirror_wbtc_decimals)
        )
    if cfg.router_mirror_token_weth:
        asset_legs.append(
            ("ETH/USDT", "WETH", cfg.router_mirror_token_weth, cfg.router_mirror_weth_decimals)
        )
    if cfg.router_mirror_token_wsol:
        asset_legs.append(
            ("SOL/USDT", "SOL", cfg.router_mirror_token_wsol, cfg.router_mirror_wsol_decimals)
        )
    if not asset_legs:
        return None

    pairs = [
        PairSpec(
            oracle_asset=oracle_asset,
            stable_address=cfg.router_mirror_token_usdc,
            stable_decimals=cfg.router_mirror_usdc_decimals,
            asset_address=asset_addr,
            asset_decimals=asset_dec,
        )
        for oracle_asset, _label, asset_addr, asset_dec in asset_legs
    ]
    # Reuse KITE_RPC_URL / chain_id from the canonical anchor config so
    # the keeper submits to the same chain the price snapshots originate
    # from. ROUTER_MIRROR_SIGNER_PK is independent of ORACLE_SIGNER_PK so
    # the router-owner key (deployer) and the oracle attestation key can
    # be rotated separately.
    return RouterPriceMirror(
        store=store,
        rpc_url=cfg.rpc_url,
        signer_pk=cfg.router_mirror_signer_pk,
        router_address=cfg.router_mirror_address,
        chain_id=cfg.chain_id,
        pairs=pairs,
        spread_bps=cfg.router_mirror_spread_bps,
    )


def _compose_on_snapshot(scheduler: PriceAnchorScheduler, mirror: RouterPriceMirror | None):
    """Fan out a single Poller `on_snapshot` to (a) the price-anchor
    scheduler and (b) the router mirror. Both run sequentially per bar
    so failures in one don't poison the other (Poller already wraps the
    callback in a try/except)."""
    if mirror is None:
        return scheduler.on_bar_async

    async def composed(asset: str) -> None:
        await scheduler.on_bar_async(asset)
        await mirror.on_snapshot_async(asset)

    return composed


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
