"""FastAPI shell for the reference momentum strategy.

The strategy isn't strictly a service — `helios deploy` packages it
as a Docker container — but a /health endpoint plus a runtime stats
view makes operations dramatically easier (and matches the rest of
the Phase 1 services). Tick cadences run in the lifespan-owned
runtime.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from momentum_v1.executor import TradeExecutor
from momentum_v1.oracle_client import OracleClient
from momentum_v1.prover_client import ProverClient
from momentum_v1.runtime import MomentumRuntime, RuntimeConfig
from momentum_v1.strategy import MomentumStrategy


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="MOMENTUM_", env_file=".env", extra="ignore")

    oracle_endpoint: str = Field(default="", validation_alias="ORACLE_ENDPOINT")
    prover_endpoint: str = Field(default="", validation_alias="PROVER_ENDPOINT")
    strategy_vault_address: str = Field(default="", validation_alias="STRATEGY_VAULT_ADDRESS")
    mock_router_address: str = Field(default="", validation_alias="MOCK_SWAP_ROUTER_ADDRESS")
    operator_pk: str = Field(default="", validation_alias="MOMENTUM_OPERATOR_PK")
    nav_oracle_pk: str = Field(default="", validation_alias="NAV_ORACLE_PK")
    allocator_address: str = Field(default="0x" + "0" * 40, validation_alias="ALLOCATOR_ADDRESS")
    declared_class_field: int = Field(default=0, validation_alias="MOMENTUM_DECLARED_CLASS_FIELD")
    # Phase-5: when running on Base Sepolia, set venue_kind=uniswap_v3 +
    # pool_fee_bps to the chosen pool's fee tier (e.g. 500 for
    # ETH/USDC 0.05%). Defaults preserve Kite/Algebra behavior.
    venue_kind: str = Field(default="algebra", validation_alias="MOMENTUM_VENUE_KIND")
    pool_fee_bps: int = Field(default=500, validation_alias="MOMENTUM_POOL_FEE_BPS")
    bar_interval_sec: int = 60
    nav_interval_sec: int = 300
    signal_threshold: float = 0.015
    lookback_bars: int = 10
    http_port: int = 8005
    # Phase-6 multi-asset: JSON dict mapping asset symbol -> raw decimals.
    # Empty string keeps the Phase-1 USD*10^18 legacy witness encoding.
    # Set to e.g. '{"USDC":18,"WBTC":8,"WETH":18,"WSOL":9}' on Kite testnet
    # to switch the runtime into raw-tokenIn mode so on-chain `amountIn`
    # matches `publicInputs[PI_AMOUNT_IN]`.
    asset_decimals_json: str = Field(default="", validation_alias="MOMENTUM_ASSET_DECIMALS_JSON")


def _parse_asset_decimals(raw: str) -> dict[str, int] | None:
    """Parse `MOMENTUM_ASSET_DECIMALS_JSON` into the runtime's
    `asset_decimals` mapping. Empty / whitespace input → None
    (preserves the Phase-1 legacy USD*10^18 witness encoding).
    Bad JSON or non-int values raise so a misconfigured deploy
    fails loudly at startup rather than silently using legacy
    semantics on a multi-decimal universe.
    """
    if not raw or not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("MOMENTUM_ASSET_DECIMALS_JSON must be a JSON object")
    out: dict[str, int] = {}
    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, int) or v < 0:
            raise ValueError("MOMENTUM_ASSET_DECIMALS_JSON entries must be {symbol: int>=0}")
        out[k] = v
    return out


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(timeout=35.0, headers={"User-Agent": "helios-momentum/0.1"})
    oracle = OracleClient(cfg.oracle_endpoint, client=http_client) if cfg.oracle_endpoint else None
    prover = ProverClient(cfg.prover_endpoint, client=http_client) if cfg.prover_endpoint else None
    executor = TradeExecutor(
        rpc_url=cfg.kite_rpc_url,
        operator_pk=cfg.operator_pk,
        strategy_vault_address=cfg.strategy_vault_address,
        mock_router_address=cfg.mock_router_address,
        chain_id=cfg.kite_chain_id,
        venue_kind=cfg.venue_kind,
        pool_fee_bps=cfg.pool_fee_bps,
    )
    strategy = MomentumStrategy(
        signal_threshold=cfg.signal_threshold, lookback_bars=cfg.lookback_bars
    )
    runtime = (
        MomentumRuntime(
            strategy=strategy,
            oracle=oracle,
            prover=prover,
            executor=executor,
            config=RuntimeConfig(
                bar_interval_sec=cfg.bar_interval_sec,
                nav_interval_sec=cfg.nav_interval_sec,
                declared_class_field=cfg.declared_class_field,
                asset_decimals=_parse_asset_decimals(cfg.asset_decimals_json),
            ),
            nav_oracle_pk=cfg.nav_oracle_pk,
            allocator_address=cfg.allocator_address,
        )
        if oracle is not None and prover is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if runtime is not None:
            runtime.start()
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.stop()
            await http_client.aclose()

    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": "momentum_v1",
            "declared_class": strategy.declared_class,
            "asset_universe": list(strategy.asset_universe),
            "live_chain_io": executor.live,
            "oracle_endpoint": cfg.oracle_endpoint,
            "prover_endpoint": cfg.prover_endpoint,
            "running": runtime is not None,
        }

    @router.get("/stats")
    async def stats() -> dict[str, object]:
        if runtime is None:
            return {"running": False}
        s = runtime.stats
        return {
            "running": True,
            "bars_observed": s.bars_observed,
            "signals_fired": s.signals_fired,
            "proofs_generated": s.proofs_generated,
            "proof_failures": s.proof_failures,
            "execs_submitted": s.execs_submitted,
            "nav_reports": s.nav_reports,
            "last_signal": s.last_signal,
            "last_error": s.last_error,
        }

    app = create_app(name="momentum_v1", settings=cfg, routers=[router])
    app.router.lifespan_context = _compose_lifespans(app.router.lifespan_context, lifespan)
    app.state.strategy = strategy  # type: ignore[attr-defined]
    app.state.executor = executor  # type: ignore[attr-defined]
    app.state.runtime = runtime  # type: ignore[attr-defined]
    return app


def _compose_lifespans(outer, inner):
    @asynccontextmanager
    async def composed(app: FastAPI) -> AsyncIterator[None]:
        async with outer(app), inner(app):
            yield

    return composed
