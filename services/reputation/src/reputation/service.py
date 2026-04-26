"""Reputation Engine service composition.

Phase 1 ships a P&L + proof-validity score (`Helios.md §8.2` simplification);
Phase 2 implements the full multi-factor formula. Reads strategy state from
Goldsky every `poll_interval_sec`, signs updates with `REPUTATION_SIGNER_PK`,
exposes them via REST (`/v1/scores/recent`, `/v1/scores/{strategy}`) and a
WebSocket feed (`/v1/scores/stream`) that the dashboard subscribes to.

The on-chain `postReputationUpdate` call is wired in WS3 e2e — until the
ReputationAnchor is deployed and `REPUTATION_ANCHOR_ADDRESS` is set, the
engine signs and broadcasts but does not submit transactions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from reputation.engine import EngineUpdate, ReputationEngine
from reputation.goldsky import GoldskyClient
from reputation.signer import ReputationSigner


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="REPUTATION_", env_file=".env", extra="ignore")

    poll_interval_sec: int = 60
    recompute_cadence_sec: int = 300
    signer_pk: str = Field(default="", validation_alias="REPUTATION_SIGNER_PK")
    anchor_address: str = Field(default="", validation_alias="REPUTATION_ANCHOR_ADDRESS")
    http_port: int = 8002


def _serialize(update: EngineUpdate) -> dict[str, object]:
    return {
        "strategy": update.rollup.strategy_id,
        "declaredClass": update.rollup.declared_class,
        "score_e4": update.outputs.score_e4,
        "pnl_term_e4": update.outputs.pnl_term_e4,
        "proof_term_e4": update.outputs.proof_term_e4,
        "inputs": {
            "realized_pnl_30d_e18": str(update.inputs.realized_pnl_30d_e18),
            "notional_e18": str(update.inputs.notional_e18),
            "proof_validity_rate_bps": update.inputs.proof_validity_rate_bps,
        },
        "signed": {
            "signer": update.signed.signer,
            "signature": "0x" + update.signed.signature.hex(),
            "actor": update.signed.update.actor,
            "actorType": int(update.signed.update.actor_type),
            "currentScore": update.signed.update.current_score,
            "lastUpdateBlock": update.signed.update.last_update_block,
            "totalAttestedTrades": update.signed.update.total_attested_trades,
            "totalRealizedPnL": str(update.signed.update.total_realized_pnl),
            "maxDrawdownBps": update.signed.update.max_drawdown_bps,
            "proofValidityRateBps": update.signed.update.proof_validity_rate_bps,
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
    )
    engine = ReputationEngine(
        goldsky=goldsky, signer=signer, poll_interval_sec=cfg.poll_interval_sec
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

    @router.websocket("/scores/stream")
    async def scores_stream(ws: WebSocket) -> None:
        await ws.accept()
        q = engine.subscribe()
        try:
            # Replay current snapshot so a freshly-connected client sees state
            # without having to wait for the next tick.
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
