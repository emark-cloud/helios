"""FastAPI shell for the reference mean_reversion strategy.

The strategy isn't strictly a service — `helios deploy` packages it
as a Docker container — but a /health endpoint plus a runtime stats
view makes operations dramatically easier (and matches the rest of
the Phase 1/2 services).
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

from mean_reversion_v1.executor import TradeExecutor
from mean_reversion_v1.oracle_client import OracleClient
from mean_reversion_v1.prover_client import ProverClient
from mean_reversion_v1.runtime import MeanReversionRuntime, RuntimeConfig
from mean_reversion_v1.strategy import MeanReversionStrategy


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="MEAN_REV_", env_file=".env", extra="ignore")

    oracle_endpoint: str = Field(default="", validation_alias="ORACLE_ENDPOINT")
    prover_endpoint: str = Field(default="", validation_alias="PROVER_ENDPOINT")
    strategy_vault_address: str = Field(default="", validation_alias="STRATEGY_VAULT_ADDRESS")
    mock_router_address: str = Field(default="", validation_alias="MOCK_SWAP_ROUTER_ADDRESS")
    operator_pk: str = Field(default="", validation_alias="MEAN_REV_OPERATOR_PK")
    nav_oracle_pk: str = Field(default="", validation_alias="NAV_ORACLE_PK")
    allocator_address: str = Field(default="0x" + "0" * 40, validation_alias="ALLOCATOR_ADDRESS")
    declared_class_field: int = Field(default=0, validation_alias="MEAN_REV_DECLARED_CLASS_FIELD")
    bar_interval_sec: int = 60
    nav_interval_sec: int = 300
    n_sigma_x100: int = 200
    stop_loss_price_usd: float = 0.0
    http_port: int = 8006
    # Phase-6 multi-asset: see momentum_v1/service.py for the same field.
    # Empty string keeps the Phase-1 USD*10^18 legacy witness encoding;
    # set to e.g. '{"USDC":18,"WBTC":8,"WETH":18,"WSOL":9}' to switch
    # the runtime into raw-tokenIn mode.
    asset_decimals_json: str = Field(
        default="", validation_alias="MEAN_REV_ASSET_DECIMALS_JSON"
    )


def _parse_asset_decimals(raw: str) -> dict[str, int] | None:
    """Same shape as `momentum_v1/service.py:_parse_asset_decimals` —
    parse `MEAN_REV_ASSET_DECIMALS_JSON` into the runtime's
    `asset_decimals` mapping. Empty input → None (legacy mode).
    Bad JSON / wrong types raise so misconfiguration fails loudly.
    """
    if not raw or not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("MEAN_REV_ASSET_DECIMALS_JSON must be a JSON object")
    out: dict[str, int] = {}
    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, int) or v < 0:
            raise ValueError(
                "MEAN_REV_ASSET_DECIMALS_JSON entries must be {symbol: int>=0}"
            )
        out[k] = v
    return out


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(
        timeout=35.0, headers={"User-Agent": "helios-mean-reversion/0.1"}
    )
    oracle = OracleClient(cfg.oracle_endpoint, client=http_client) if cfg.oracle_endpoint else None
    prover = ProverClient(cfg.prover_endpoint, client=http_client) if cfg.prover_endpoint else None
    executor = TradeExecutor(
        rpc_url=cfg.kite_rpc_url,
        operator_pk=cfg.operator_pk,
        strategy_vault_address=cfg.strategy_vault_address,
        mock_router_address=cfg.mock_router_address,
        chain_id=cfg.kite_chain_id,
    )
    strategy = MeanReversionStrategy(
        n_sigma_x100=cfg.n_sigma_x100,
        stop_loss_price_usd=cfg.stop_loss_price_usd,
    )
    runtime = (
        MeanReversionRuntime(
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
            "service": "mean_reversion_v1",
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

    app = create_app(name="mean_reversion_v1", settings=cfg, routers=[router])
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
