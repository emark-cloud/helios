"""FastAPI shell for the reference mean_reversion strategy.

The strategy isn't strictly a service — `helios deploy` packages it
as a Docker container — but a /health endpoint plus a runtime stats
view makes operations dramatically easier (and matches the rest of
the Phase 1/2 services).
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
    ensure_params_committed,
)
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from web3 import Web3

from mean_reversion_v1.executor import TradeExecutor
from mean_reversion_v1.oracle_client import OracleClient
from mean_reversion_v1.prover_client import ProverClient
from mean_reversion_v1.runtime import MeanReversionRuntime, RuntimeConfig, Web3BlockProvider
from mean_reversion_v1.strategy import MeanReversionStrategy

_log = logging.getLogger(__name__)


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
    asset_decimals_json: str = Field(default="", validation_alias="MEAN_REV_ASSET_DECIMALS_JSON")
    asset_universe_addresses_json: str = Field(
        default="",
        validation_alias="MEAN_REV_ASSET_UNIVERSE_ADDRESSES_JSON",
    )
    # Optional Base/Arb-scoped symbolic universe override. The default
    # `MeanReversionStrategy.asset_universe` is `("USDC","WBTC","WETH","WSOL")`
    # — correct for Kite, but on Base the on-chain vault universe is
    # `[Base mUSDC, WETH9]`. Setting `MEAN_REV_ASSET_UNIVERSE_SYMBOLS_JSON`
    # to e.g. `["USDC","WETH"]` realigns the strategy's symbol→index
    # mapping with the address slot order so signals don't get
    # silently routed to the wrong asset (see runtime lockstep guard).
    asset_universe_symbols_json: str = Field(
        default="",
        validation_alias="MEAN_REV_ASSET_UNIVERSE_SYMBOLS_JSON",
    )
    strategy_registry_address: str = Field(default="", validation_alias="STRATEGY_REGISTRY")


def _parse_asset_universe_addresses(raw: str) -> list[str] | None:
    """Parse `MEAN_REV_ASSET_UNIVERSE_ADDRESSES_JSON` into the 8-entry
    list `MeanReversionRuntime` requires. Empty input returns `None`
    (symbol-fallback for local tests); wrong arity raises so a
    half-configured deploy fails loudly at startup."""
    if not raw or not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("MEAN_REV_ASSET_UNIVERSE_ADDRESSES_JSON must be a JSON list")
    if len(parsed) != 8:
        raise ValueError(
            f"MEAN_REV_ASSET_UNIVERSE_ADDRESSES_JSON must have exactly 8 entries, got {len(parsed)}"
        )
    out: list[str] = []
    for entry in parsed:
        if not isinstance(entry, str):
            raise ValueError(
                "MEAN_REV_ASSET_UNIVERSE_ADDRESSES_JSON entries must be address strings"
            )
        out.append(entry)
    return out


def _parse_asset_universe_symbols(raw: str) -> tuple[str, ...] | None:
    """Parse `MEAN_REV_ASSET_UNIVERSE_SYMBOLS_JSON` into the strategy's
    symbolic universe tuple. Empty input returns `None` (use the
    strategy's class default). Wrong shape raises so a half-configured
    deploy fails loudly at startup."""
    if not raw or not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("MEAN_REV_ASSET_UNIVERSE_SYMBOLS_JSON must be a non-empty JSON list")
    out: list[str] = []
    for entry in parsed:
        if not isinstance(entry, str) or not entry:
            raise ValueError(
                "MEAN_REV_ASSET_UNIVERSE_SYMBOLS_JSON entries must be non-empty symbol strings"
            )
        out.append(entry)
    return tuple(out)


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
            raise ValueError("MEAN_REV_ASSET_DECIMALS_JSON entries must be {symbol: int>=0}")
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
        asset_universe=_parse_asset_universe_symbols(cfg.asset_universe_symbols_json),
    )
    w3: Web3 | None = None
    block_provider: Web3BlockProvider | None = None
    if cfg.kite_rpc_url:
        w3 = Web3(Web3.HTTPProvider(cfg.kite_rpc_url))
        block_provider = Web3BlockProvider(w3)

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
            asset_universe_addresses=_parse_asset_universe_addresses(
                cfg.asset_universe_addresses_json
            ),
            block_provider=block_provider,
        )
        if oracle is not None and prover is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Bring-up: commit the strategy's Poseidon paramsHash to the
        # registry before the bar loop fires (`StrategyVault.sol:470`).
        # Idempotent — restarts read-and-skip; mismatched hash is fatal.
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
                _log.exception("mean_reversion.params_hash.mismatch")
                raise
            except Exception:
                _log.exception("mean_reversion.params_hash.commit_failed")
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
            "signals_unfundable": s.signals_unfundable,
            "execs_submitted": s.execs_submitted,
            "nav_reports": s.nav_reports,
            "last_seeded_nav_usd": s.last_seeded_nav_usd,
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
