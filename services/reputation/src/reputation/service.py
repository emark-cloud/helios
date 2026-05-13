"""Reputation Engine service composition.

Phase 2 (`Helios.md §8.2`): full multi-component score, cohort-relative
performance, /v1/audit endpoint exposing the breakdown.

Shadow-mode signing (`docs/phase2-plan.md` WS2.A): `REPUTATION_TYPEHASH_VERSION`
defaults to `"1"` and stays there until WS3.A's `ReputationAnchor` v2 deploys.
The engine still computes `componentsHash` and serves it via /v1/audit so the
frontend can render the §8.2 breakdown immediately.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from reputation import score as _score
from reputation.anchor import AnchorPoster, RegistryActiveCheck
from reputation.cohort import CohortStats
from reputation.engine import AllocatorEngineUpdate, EngineUpdate, ReputationEngine
from reputation.goldsky import GoldskyClient
from reputation.score import CohortContext
from reputation.signer import ReputationSigner


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="REPUTATION_", env_file=".env", extra="ignore")

    poll_interval_sec: int = 60
    recompute_cadence_sec: int = 300
    signer_pk: str = Field(default="", validation_alias="REPUTATION_SIGNER_PK")
    anchor_address: str = Field(default="", validation_alias="REPUTATION_ANCHOR_ADDRESS")
    typehash_version: str = Field(default="1", validation_alias="REPUTATION_TYPEHASH_VERSION")
    # WS11 follow-up — pre-flight every submission against the active
    # registry set to skip legacy actors the bound registries no longer
    # recognise (`StrategyNotFound` 0x5be2b482 / `AllocatorNotFound`).
    # Either may be empty: the filter then defers to the anchor's own
    # checks for that actor type.
    strategy_registry_address: str = Field(
        default="", validation_alias="REPUTATION_STRATEGY_REGISTRY_ADDRESS"
    )
    allocator_registry_address: str = Field(
        default="", validation_alias="REPUTATION_ALLOCATOR_REGISTRY_ADDRESS"
    )
    http_port: int = 8002


def _serialize_cohort(c: CohortStats) -> dict[str, object]:
    return {
        "size": c.size,
        "median": c.median,
        "iqr": c.iqr,
        "is_fallback": c.is_fallback,
    }


def _serialize_cohort_context(ctx: CohortContext) -> dict[str, object]:
    return {
        "win_7d": _serialize_cohort(ctx.win_7d),
        "win_30d": _serialize_cohort(ctx.win_30d),
        "win_90d": _serialize_cohort(ctx.win_90d),
    }


def _serialize_components(update: EngineUpdate) -> dict[str, object]:
    c = update.outputs.components
    return {
        "performance": c.performance,
        "risk": c.risk,
        "proof": c.proof,
        "stake": c.stake,
        "age": c.age,
    }


def _serialize_perf_breakdown(update: EngineUpdate) -> dict[str, object]:
    p = update.outputs.perf_breakdown
    return {
        "sharpe_7d": p.sharpe_7d,
        "sharpe_30d": p.sharpe_30d,
        "sharpe_90d": p.sharpe_90d,
        "norm_7d": p.norm_7d,
        "norm_30d": p.norm_30d,
        "norm_90d": p.norm_90d,
    }


def _serialize_allocator_audit(update: AllocatorEngineUpdate) -> dict[str, object]:
    """Allocator-shaped /v1/audit response. Mirrors the strategy shape on
    the wire (`actor`, `score_e4`, `components`, `components_hash`,
    `inputs`, `posted`, `signed`) but emits the four allocator
    components and the per-allocator inputs from `AllocatorScoreInputs`.
    `actorType=1` lets the frontend distinguish strategy vs allocator
    audits without sniffing field shape."""
    c = update.outputs.components
    s = update.state
    inp = update.inputs
    return {
        "actor": s.allocator_id,
        "actorType": 1,  # ActorType.ALLOCATOR — frontend `/audit` switch key.
        "declaredClass": s.declared_class,
        "score_e4": update.outputs.score_e4,
        "components": {
            "pnl": c.pnl,
            "drawdown": c.drawdown,
            "retention": c.retention,
            "stake": c.stake,
        },
        "components_hash": "0x" + update.outputs.components_hash.hex(),
        "weights": {
            "pnl": _score.W_ALLOC_PNL,
            "drawdown": _score.W_ALLOC_DRAWDOWN,
            "retention": _score.W_ALLOC_RETENTION,
            "stake": _score.W_ALLOC_STAKE,
        },
        "inputs": {
            "aggregate_pnl_above_hwm_e18": str(inp.aggregate_pnl_above_hwm_e18),
            "aggregate_capital_e18": str(inp.aggregate_capital_e18),
            "breach_total_count": inp.breach_total_count,
            "breach_response_count": inp.breach_response_count,
            "users_at_window_start": inp.users_at_window_start,
            "users_at_window_end": inp.users_at_window_end,
            "stake_e18": str(inp.stake_e18),
            "max_stake_in_class_e18": str(inp.max_stake_in_class_e18),
        },
        "posted": (
            None
            if update.posted is None
            else {
                "submitted": update.posted.submitted,
                "tx_hash": update.posted.tx_hash,
                "error": update.posted.error,
            }
        ),
        "signed": {
            "signer": update.signed.signer,
            "signature": "0x" + update.signed.signature.hex(),
            "typehash_version": update.signed.typehash_version,
            "actor": update.signed.update.actor,
            "actorType": int(update.signed.update.actor_type),
            "currentScore": update.signed.update.current_score,
            "lastUpdateBlock": update.signed.update.last_update_block,
            "componentsHash": "0x" + update.signed.update.components_hash.rjust(32, b"\x00").hex(),
        },
    }


def _serialize(update: EngineUpdate) -> dict[str, object]:
    return {
        "strategy": update.state.strategy_id,
        "declaredClass": update.state.declared_class,
        "score_e4": update.outputs.score_e4,
        "components": _serialize_components(update),
        "components_hash": "0x" + update.outputs.components_hash.hex(),
        "perf_breakdown": _serialize_perf_breakdown(update),
        "cohort": _serialize_cohort_context(update.cohort),
        "inputs": {
            "stake_e18": str(update.inputs.stake_e18),
            "max_stake_in_class_e18": str(update.inputs.max_stake_in_class_e18),
            "trades_attested": update.inputs.trades_attested,
            "max_drawdown_bps_90d": update.inputs.max_drawdown_bps_90d,
            "valid_proofs": update.inputs.valid_proofs,
            "total_proof_attempts": update.inputs.total_proof_attempts,
        },
        "posted": (
            None
            if update.posted is None
            else {
                "submitted": update.posted.submitted,
                "tx_hash": update.posted.tx_hash,
                "error": update.posted.error,
            }
        ),
        "signed": {
            "signer": update.signed.signer,
            "signature": "0x" + update.signed.signature.hex(),
            "typehash_version": update.signed.typehash_version,
            "actor": update.signed.update.actor,
            "actorType": int(update.signed.update.actor_type),
            "currentScore": update.signed.update.current_score,
            "lastUpdateBlock": update.signed.update.last_update_block,
            "totalAttestedTrades": update.signed.update.total_attested_trades,
            "totalRealizedPnL": str(update.signed.update.total_realized_pnl),
            "maxDrawdownBps": update.signed.update.max_drawdown_bps,
            "proofValidityRateBps": update.signed.update.proof_validity_rate_bps,
            "componentsHash": "0x" + update.signed.update.components_hash.rjust(32, b"\x00").hex(),
        },
    }


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "helios-reputation/0.1"})
    goldsky = GoldskyClient(endpoint=cfg.goldsky_endpoint, client=http_client)
    signer = ReputationSigner(
        private_key_hex=cfg.signer_pk,
        chain_id=cfg.kite_chain_id,
        anchor_address=cfg.anchor_address or "0x" + "0" * 40,
        typehash_version=cfg.typehash_version,
    )
    registry_check = (
        RegistryActiveCheck(
            rpc_url=cfg.kite_rpc_url,
            strategy_registry=cfg.strategy_registry_address,
            allocator_registry=cfg.allocator_registry_address,
        )
        if (cfg.strategy_registry_address or cfg.allocator_registry_address)
        else None
    )
    anchor = AnchorPoster(
        rpc_url=cfg.kite_rpc_url,
        signer_pk=cfg.signer_pk,
        anchor_address=cfg.anchor_address,
        chain_id=cfg.kite_chain_id,
        typehash_version=cfg.typehash_version,
        registry_check=registry_check,
    )
    engine = ReputationEngine(
        goldsky=goldsky,
        signer=signer,
        poll_interval_sec=cfg.poll_interval_sec,
        anchor=anchor,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        engine.start()
        try:
            yield
        finally:
            await engine.stop()
            await http_client.aclose()

    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": "reputation",
            "poll_interval_sec": cfg.poll_interval_sec,
            "scenario_mode": int(cfg.scenario_mode),
            "signer": signer.signer_address,
            "anchor": cfg.anchor_address,
            "goldsky_endpoint": cfg.goldsky_endpoint,
            "typehash_version": signer.typehash_version,
        }

    @router.get("/scores/recent")
    async def scores_recent() -> dict[str, object]:
        latest = engine.latest
        return {"count": len(latest), "scores": [_serialize(u) for u in latest.values()]}

    @router.get("/scores/{strategy}")
    async def score_for(strategy: str) -> dict[str, object]:
        update = engine.latest.get(strategy)
        if update is None:
            raise HTTPException(status_code=404, detail=f"no score for {strategy}")
        return _serialize(update)

    @router.get("/audit/{actor}")
    async def audit_for(actor: str) -> dict[str, object]:
        """Full breakdown for one actor — strategy or allocator.

        Strategies (§8.2) return five components, cohort stats per window,
        raw + normalized Sharpes, plus the on-chain `componentsHash`.
        Allocators (WS5.A) return the four-component breakdown plus
        `componentsHash`. Frontend `/audit` page consumes both shapes;
        the `actorType` field tells it which.
        """
        allocator_update = engine.latest_allocators.get(actor)
        if allocator_update is not None:
            return _serialize_allocator_audit(allocator_update)
        update = engine.latest.get(actor)
        if update is None:
            raise HTTPException(status_code=404, detail=f"no audit for {actor}")
        return {
            "actor": update.state.strategy_id,
            "declaredClass": update.state.declared_class,
            "score_e4": update.outputs.score_e4,
            "components": _serialize_components(update),
            "components_hash": "0x" + update.outputs.components_hash.hex(),
            "perf_breakdown": _serialize_perf_breakdown(update),
            "cohort": _serialize_cohort_context(update.cohort),
            "weights": {
                "performance": _score.W_PERF,
                "risk": _score.W_RISK,
                "proof": _score.W_PROOF,
                "stake": _score.W_STAKE,
                "age": _score.W_AGE,
            },
            "inputs": {
                "stake_e18": str(update.inputs.stake_e18),
                "max_stake_in_class_e18": str(update.inputs.max_stake_in_class_e18),
                "trades_attested": update.inputs.trades_attested,
                "max_drawdown_bps_90d": update.inputs.max_drawdown_bps_90d,
                "valid_proofs": update.inputs.valid_proofs,
                "total_proof_attempts": update.inputs.total_proof_attempts,
            },
            # PR4: surface the soundness caveat from `phase2-review.md` —
            # `proof` is binary 0/1 in Phase 2 (no rejected proofs are
            # observable from the subgraph), so a `1.0` value means "no
            # rejections seen" rather than "100% proof correctness." The
            # frontend uses this flag to render the caveat next to the
            # "verified" badge instead of treating it as a clean signal.
            "proof_score_is_binary": True,
        }

    @router.websocket("/scores/stream")
    async def scores_stream(ws: WebSocket) -> None:
        await ws.accept()
        q = engine.subscribe()
        try:
            for u in engine.latest.values():
                await ws.send_json(_serialize(u))
            while True:
                update = await q.get()
                await ws.send_json(_serialize(update))
        except WebSocketDisconnect:
            pass
        finally:
            engine.unsubscribe(q)

    app = create_app(name="reputation", settings=cfg, routers=[router])
    app.router.lifespan_context = _compose_lifespans(app.router.lifespan_context, lifespan)
    app.state.engine = engine  # type: ignore[attr-defined]
    app.state.signer = signer  # type: ignore[attr-defined]
    app.state.goldsky = goldsky  # type: ignore[attr-defined]
    return app


def _compose_lifespans(outer, inner):
    @asynccontextmanager
    async def composed(app: FastAPI) -> AsyncIterator[None]:
        async with outer(app), inner(app):
            yield

    return composed
