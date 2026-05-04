"""FastAPI shell for the reference yield-rotation strategy.

Mirrors the momentum/MR shells — `/health` is provided by the service
template; `/v1/` exposes manifest + runtime stats. Tick cadences run in
the lifespan-owned runtime.

Subscriptions (the (oracle market id, registry market id) tuples the
runtime polls) are configured via two env vars:
  * `YIELD_ROT_MARKET_IDS` — comma-separated oracle market ids
    (matching the oracle's `YIELD_MARKETS` config), e.g.
    `AAVE_USDC,COMPOUND_USDC`
  * `YIELD_ROT_REGISTRY_IDS` — comma-separated uint64s aligned 1-to-1
    with `MARKET_IDS`, e.g. `1,2`

The registry ids are also used as the strategy's allowlist and must
match the on-chain `markets_allowlist_root` set on the registry.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from yield_rotation_v1.executor import TradeExecutor
from yield_rotation_v1.oracle_client import YieldOracleClient
from yield_rotation_v1.prover_client import ProverClient
from yield_rotation_v1.runtime import RuntimeConfig, YieldRotationRuntime
from yield_rotation_v1.strategy import YieldRotationStrategy


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="YIELD_ROT_", env_file=".env", extra="ignore")

    oracle_endpoint: str = Field(default="", validation_alias="ORACLE_ENDPOINT")
    prover_endpoint: str = Field(default="", validation_alias="PROVER_ENDPOINT")
    strategy_vault_address: str = Field(default="", validation_alias="STRATEGY_VAULT_ADDRESS")
    operator_pk: str = Field(default="", validation_alias="YIELD_ROT_OPERATOR_PK")
    nav_oracle_pk: str = Field(default="", validation_alias="NAV_ORACLE_PK")
    allocator_address: str = Field(default="0x" + "0" * 40, validation_alias="ALLOCATOR_ADDRESS")
    declared_class_field: int = Field(default=0, validation_alias="YIELD_ROT_DECLARED_CLASS_FIELD")
    market_ids: str = Field(default="", validation_alias="YIELD_ROT_MARKET_IDS")
    registry_ids: str = Field(default="", validation_alias="YIELD_ROT_REGISTRY_IDS")
    signal_threshold_bps: int = 80
    bridging_cost_bps: int = 30
    yield_interval_sec: int = 300
    nav_interval_sec: int = 300
    http_port: int = 8007


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(
        timeout=35.0, headers={"User-Agent": "helios-yield-rotation/0.1"}
    )
    oracle = (
        YieldOracleClient(cfg.oracle_endpoint, client=http_client) if cfg.oracle_endpoint else None
    )
    prover = ProverClient(cfg.prover_endpoint, client=http_client) if cfg.prover_endpoint else None
    executor = TradeExecutor(
        rpc_url=cfg.kite_rpc_url,
        operator_pk=cfg.operator_pk,
        strategy_vault_address=cfg.strategy_vault_address,
        chain_id=cfg.kite_chain_id,
    )

    subs = _parse_subscriptions(cfg.market_ids, cfg.registry_ids)
    allowlist = tuple(reg_id for _, reg_id in subs) if subs else (1, 2)

    strategy = YieldRotationStrategy(
        allowlisted_markets=allowlist,
        signal_threshold_bps=cfg.signal_threshold_bps,
        bridging_cost_bps=cfg.bridging_cost_bps,
    )
    runtime = (
        YieldRotationRuntime(
            strategy=strategy,
            oracle=oracle,
            prover=prover,
            executor=executor,
            config=RuntimeConfig(
                yield_interval_sec=cfg.yield_interval_sec,
                nav_interval_sec=cfg.nav_interval_sec,
                declared_class_field=cfg.declared_class_field,
            ),
            market_subscriptions=subs,
            nav_oracle_pk=cfg.nav_oracle_pk,
            allocator_address=cfg.allocator_address,
        )
        if oracle is not None and prover is not None and subs
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
            "service": "yield_rotation_v1",
            "declared_class": strategy.declared_class,
            "allowlisted_markets": list(strategy.allowlisted_markets),
            "subscriptions": [{"market_id": m, "registry_id": r} for m, r in subs],
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
            "ticks_observed": s.ticks_observed,
            "signals_fired": s.signals_fired,
            "proofs_generated": s.proofs_generated,
            "proof_failures": s.proof_failures,
            "execs_submitted": s.execs_submitted,
            "nav_reports": s.nav_reports,
            "last_signal": s.last_signal,
            "last_error": s.last_error,
        }

    app = create_app(name="yield_rotation_v1", settings=cfg, routers=[router])
    app.router.lifespan_context = _compose_lifespans(app.router.lifespan_context, lifespan)
    app.state.strategy = strategy  # type: ignore[attr-defined]
    app.state.executor = executor  # type: ignore[attr-defined]
    app.state.runtime = runtime  # type: ignore[attr-defined]
    return app


def _parse_subscriptions(market_ids_csv: str, registry_ids_csv: str) -> list[tuple[str, int]]:
    if not market_ids_csv or not registry_ids_csv:
        return []
    markets = [s.strip() for s in market_ids_csv.split(",") if s.strip()]
    regs_raw = [s.strip() for s in registry_ids_csv.split(",") if s.strip()]
    if len(markets) != len(regs_raw):
        raise ValueError("YIELD_ROT_MARKET_IDS and YIELD_ROT_REGISTRY_IDS must be the same length")
    return [(m, int(r)) for m, r in zip(markets, regs_raw, strict=True)]


def _compose_lifespans(outer, inner):
    @asynccontextmanager
    async def composed(app: FastAPI) -> AsyncIterator[None]:
        async with outer(app), inner(app):
            yield

    return composed
