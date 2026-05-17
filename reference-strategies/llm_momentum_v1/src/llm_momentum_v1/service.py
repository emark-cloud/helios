"""FastAPI shell for the reference momentum strategy.

The strategy isn't strictly a service — `helios deploy` packages it
as a Docker container — but a /health endpoint plus a runtime stats
view makes operations dramatically easier (and matches the rest of
the Phase 1 services). Tick cadences run in the lifespan-owned
runtime.
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

from llm_momentum_v1.executor import TradeExecutor
from llm_momentum_v1.oracle_client import OracleClient
from llm_momentum_v1.prover_client import ProverClient
from llm_momentum_v1.runtime import LLMMomentumRuntime, RuntimeConfig, Web3BlockProvider
from llm_momentum_v1.strategy import LLMMomentumStrategy

_log = logging.getLogger(__name__)


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_MOMENTUM_", env_file=".env", extra="ignore")

    oracle_endpoint: str = Field(default="", validation_alias="ORACLE_ENDPOINT")
    prover_endpoint: str = Field(default="", validation_alias="PROVER_ENDPOINT")
    strategy_vault_address: str = Field(default="", validation_alias="STRATEGY_VAULT_ADDRESS")
    mock_router_address: str = Field(default="", validation_alias="MOCK_SWAP_ROUTER_ADDRESS")
    operator_pk: str = Field(default="", validation_alias="LLM_MOMENTUM_OPERATOR_PK")
    nav_oracle_pk: str = Field(default="", validation_alias="NAV_ORACLE_PK")
    allocator_address: str = Field(default="0x" + "0" * 40, validation_alias="ALLOCATOR_ADDRESS")
    declared_class_field: int = Field(
        default=0, validation_alias="LLM_MOMENTUM_DECLARED_CLASS_FIELD"
    )
    # Phase-5: when running on Base Sepolia, set venue_kind=uniswap_v3 +
    # pool_fee_bps to the chosen pool's fee tier (e.g. 500 for
    # ETH/USDC 0.05%). Defaults preserve Kite/Algebra behavior.
    venue_kind: str = Field(default="algebra", validation_alias="LLM_MOMENTUM_VENUE_KIND")
    pool_fee_bps: int = Field(default=500, validation_alias="LLM_MOMENTUM_POOL_FEE_BPS")
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
    asset_decimals_json: str = Field(
        default="", validation_alias="LLM_MOMENTUM_ASSET_DECIMALS_JSON"
    )
    # 8-entry on-chain ERC-20 address list mapped 1:1 to
    # `LLMMomentumStrategy.asset_universe`. The runtime needs the real
    # addresses (not just symbols) to embed `assetIn`/`assetOut` in
    # the witness's `publicInputs[PI_ASSET_*]` for `executeWithProof`.
    # Empty string keeps the symbol-fallback (Phase-1 dry-run); on
    # Kite testnet set to JSON of `[mUSDC, mWBTC, mWETH, mSOL, "", "", "", ""]`.
    asset_universe_addresses_json: str = Field(
        default="",
        validation_alias="LLM_MOMENTUM_ASSET_UNIVERSE_ADDRESSES_JSON",
    )
    # Optional Base/Arb-scoped symbolic universe override. The default
    # `LLMMomentumStrategy.asset_universe` is `("USDC","WBTC","WETH","WSOL")`
    # — correct for Kite, but on Base the on-chain vault universe is
    # `[Base mUSDC, WETH9]`. Setting `LLM_MOMENTUM_ASSET_UNIVERSE_SYMBOLS_JSON`
    # to e.g. `["USDC","WETH"]` realigns the strategy's symbol→index
    # mapping with the address slot order so signals don't get
    # silently routed to the wrong asset (see runtime lockstep guard).
    asset_universe_symbols_json: str = Field(
        default="",
        validation_alias="LLM_MOMENTUM_ASSET_UNIVERSE_SYMBOLS_JSON",
    )
    # Address of the deployed StrategyRegistry that gates
    # `_activeParamsHash` (`StrategyVault.sol:470`). Read once on
    # startup to commit the strategy's Poseidon paramsHash; never read
    # in the hot path. Required for Kite testnet — local tests can
    # leave empty and skip the lifespan commit.
    strategy_registry_address: str = Field(default="", validation_alias="STRATEGY_REGISTRY")

    # ── LLM-specific knobs ──────────────────────────────────────────
    # Anthropic model id. Defaults to Haiku for cost/latency on a 1-bar
    # cadence; swap to Sonnet or Opus for more deliberative decisions.
    anthropic_model: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias="LLM_MOMENTUM_ANTHROPIC_MODEL",
    )
    # Confidence floor — model decisions below this confidence are
    # treated as HOLD. The on-chain params hash bounds the trade shape;
    # this knob bounds *whether* a trade fires at all.
    min_confidence: float = Field(default=0.6, validation_alias="LLM_MOMENTUM_MIN_CONFIDENCE")
    # Max output tokens. Tool-use response is small; 512 is generous.
    max_tokens: int = Field(default=512, validation_alias="LLM_MOMENTUM_MAX_TOKENS")


def _parse_asset_universe_addresses(raw: str) -> list[str] | None:
    """Parse `LLM_MOMENTUM_ASSET_UNIVERSE_ADDRESSES_JSON` into the 8-entry
    list `LLMMomentumRuntime` requires (`runtime.py:128-129`). Empty input
    returns `None` so the runtime falls back to symbol-form for local
    tests; non-list / wrong-arity / non-string entries raise so a
    half-configured deploy fails loudly at startup."""
    if not raw or not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("LLM_MOMENTUM_ASSET_UNIVERSE_ADDRESSES_JSON must be a JSON list")
    if len(parsed) != 8:
        raise ValueError(
            "LLM_MOMENTUM_ASSET_UNIVERSE_ADDRESSES_JSON must have exactly 8 entries, "
            f"got {len(parsed)}"
        )
    out: list[str] = []
    for entry in parsed:
        if not isinstance(entry, str):
            raise ValueError(
                "LLM_MOMENTUM_ASSET_UNIVERSE_ADDRESSES_JSON entries must be address strings"
            )
        out.append(entry)
    return out


def _parse_asset_universe_symbols(raw: str) -> tuple[str, ...] | None:
    """Parse `LLM_MOMENTUM_ASSET_UNIVERSE_SYMBOLS_JSON` into the strategy's
    symbolic universe tuple. Empty input returns `None` (use the
    strategy's class default). Wrong shape raises so a half-configured
    deploy fails loudly at startup."""
    if not raw or not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("LLM_MOMENTUM_ASSET_UNIVERSE_SYMBOLS_JSON must be a non-empty JSON list")
    out: list[str] = []
    for entry in parsed:
        if not isinstance(entry, str) or not entry:
            raise ValueError(
                "LLM_MOMENTUM_ASSET_UNIVERSE_SYMBOLS_JSON entries must be non-empty symbol strings"
            )
        out.append(entry)
    return tuple(out)


def _parse_asset_decimals(raw: str) -> dict[str, int] | None:
    """Parse `LLM_MOMENTUM_ASSET_DECIMALS_JSON` into the runtime's
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
        raise ValueError("LLM_MOMENTUM_ASSET_DECIMALS_JSON must be a JSON object")
    out: dict[str, int] = {}
    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, int) or v < 0:
            raise ValueError("LLM_MOMENTUM_ASSET_DECIMALS_JSON entries must be {symbol: int>=0}")
        out[k] = v
    return out


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(timeout=35.0, headers={"User-Agent": "helios-llm-momentum/0.1"})
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
    strategy = LLMMomentumStrategy(
        signal_threshold=cfg.signal_threshold,
        lookback_bars=cfg.lookback_bars,
        asset_universe=_parse_asset_universe_symbols(cfg.asset_universe_symbols_json),
        model=cfg.anthropic_model,
        min_confidence=cfg.min_confidence,
        max_tokens=cfg.max_tokens,
    )
    # Live RPC is required to (a) read `paramsHashOf` + commit on
    # startup, (b) feed `Web3BlockProvider` so the witness's block
    # window aligns with chain head. Reuse a single Web3 across both
    # paths so the operator only points at one RPC URL.
    w3: Web3 | None = None
    block_provider: Web3BlockProvider | None = None
    if cfg.kite_rpc_url:
        w3 = build_resilient_web3(cfg.kite_rpc_url)
        block_provider = Web3BlockProvider(w3)

    runtime = (
        LLMMomentumRuntime(
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
        # registry before the bar loop starts firing. `executeWithProof`
        # will revert `ParamsHashMismatch` until this lands. Idempotent —
        # subsequent restarts read-and-skip. Hard fail on a stored hash
        # that doesn't match what this container would build, since the
        # registry has no rotate path.
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
                _log.exception("llm_momentum.params_hash.mismatch")
                raise
            except Exception:
                _log.exception("llm_momentum.params_hash.commit_failed")
                # Don't crash the container on transient RPC errors —
                # the bar loop's per-tick executor will surface the
                # underlying issue (revert) on the next signal.
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
            "service": "llm_momentum_v1",
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
            "last_seeded_nav_usd": s.last_seeded_nav_usd,
            "last_signal": s.last_signal,
            "last_error": s.last_error,
        }

    app = create_app(name="llm_momentum_v1", settings=cfg, routers=[router])
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
