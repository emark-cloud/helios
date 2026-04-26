"""FastAPI shell for the reference momentum strategy.

The strategy isn't strictly a service — `helios deploy` packages it
as a Docker container — but a /health endpoint plus a runtime stats
view makes operations dramatically easier (and matches the rest of
the Phase 1 services). Tick cadences run in the lifespan-owned
runtime.
"""

from __future__ import annotations

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
    bar_interval_sec: int = 60
    nav_interval_sec: int = 300
    signal_threshold: float = 0.015
    lookback_bars: int = 10
    http_port: int = 8005


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
