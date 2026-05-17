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

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from helios.runtime import (
    ParamsHashMismatchError,
    build_resilient_web3,
    ensure_params_committed,
)
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from web3 import Web3

from yield_rotation_v1.executor import TradeExecutor
from yield_rotation_v1.oracle_client import YieldOracleClient
from yield_rotation_v1.prover_client import ProverClient
from yield_rotation_v1.runtime import RuntimeConfig, Web3BlockProvider, YieldRotationRuntime
from yield_rotation_v1.strategy import YieldRotationStrategy

_log = logging.getLogger(__name__)


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
    # Phase-5: Arbitrum-Sepolia deploys set venue_kind=aave_v3 and
    # lending_pool_address to the chosen pool (canonical Aave V3 or
    # the SDK's MockYieldVault fallback). Default keeps Phase-2 Kite
    # behavior (proof-only, no on-chain trades).
    venue_kind: str = Field(default="passive", validation_alias="YIELD_ROT_VENUE_KIND")
    lending_pool_address: str = Field(default="", validation_alias="YIELD_ROT_LENDING_POOL_ADDRESS")
    signal_threshold_bps: int = 80
    bridging_cost_bps: int = 30
    yield_interval_sec: int = 300
    nav_interval_sec: int = 300
    http_port: int = 8007
    strategy_registry_address: str = Field(default="", validation_alias="STRATEGY_REGISTRY")
    asset_decimals_json: str = Field(default="", validation_alias="YIELD_ROT_ASSET_DECIMALS_JSON")


def _parse_asset_decimals(raw: str) -> dict[str, int] | None:
    """Parse `YIELD_ROT_ASSET_DECIMALS_JSON` into the runtime's
    `asset_decimals` mapping. Empty / whitespace input → None
    (preserves the legacy USD*10^18 NAV encoding used on Kite).
    Bad JSON or non-int values raise so a misconfigured deploy fails
    loudly at startup rather than silently mis-scaling NAV on a
    non-18-dec chain.
    """
    if not raw or not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("YIELD_ROT_ASSET_DECIMALS_JSON must be a JSON object")
    out: dict[str, int] = {}
    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, int) or v < 0:
            raise ValueError("YIELD_ROT_ASSET_DECIMALS_JSON entries must be {symbol: int>=0}")
        out[k] = v
    return out


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
        lending_pool_address=cfg.lending_pool_address,
        venue_kind=cfg.venue_kind,
    )

    subs = _parse_subscriptions(cfg.market_ids, cfg.registry_ids)
    allowlist = tuple(reg_id for _, reg_id in subs) if subs else (1, 2)

    strategy = YieldRotationStrategy(
        allowlisted_markets=allowlist,
        signal_threshold_bps=cfg.signal_threshold_bps,
        bridging_cost_bps=cfg.bridging_cost_bps,
    )
    w3: Web3 | None = None
    block_provider: Web3BlockProvider | None = None
    if cfg.kite_rpc_url:
        w3 = build_resilient_web3(cfg.kite_rpc_url)
        block_provider = Web3BlockProvider(w3)

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
                asset_decimals=_parse_asset_decimals(cfg.asset_decimals_json),
            ),
            market_subscriptions=subs,
            nav_oracle_pk=cfg.nav_oracle_pk,
            allocator_address=cfg.allocator_address,
            block_provider=block_provider,
        )
        if oracle is not None and prover is not None and subs
        else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Bring-up: commit the strategy's Poseidon paramsHash to the
        # registry before the bar loop fires (`StrategyVault.sol:470`).
        # YR's hash is narrower (just threshold + bridging cost).
        if (
            runtime is not None
            and w3 is not None
            and cfg.strategy_registry_address
            and cfg.operator_pk
            and cfg.strategy_vault_address
        ):
            try:
                ensure_params_committed(
                    w3=w3,
                    registry_address=cfg.strategy_registry_address,
                    vault_address=cfg.strategy_vault_address,
                    params_hash=strategy.params_hash(),
                    operator_pk=cfg.operator_pk,
                )
            except ParamsHashMismatchError:
                _log.exception("yield_rotation.params_hash.mismatch")
                raise
            except Exception:
                _log.exception("yield_rotation.params_hash.commit_failed")
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
            "signals_unfundable": s.signals_unfundable,
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
