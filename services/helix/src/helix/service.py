"""Helix allocator service composition.

Mirrors Sentinel's surface (`Helios.md §11.3`) so the frontend's
allocator-picker (WS6.B) can hit either service interchangeably:

  * `POST /v1/users/{user}/meta-strategy` — accept a signed meta-strategy
  * `GET  /v1/users/{user}/dashboard`     — composite dashboard payload
  * `GET  /v1/strategies`                 — public directory with filters
  * `WS   /v1/users/{user}/events`        — per-user event stream

Helix is built strictly on top of `AllocatorRuntime` — no on-chain or
Goldsky logic lives in this service. That's the §11.4 quality signal:
"Helix is built ground-up on the AllocatorSDK from a fresh
perspective." Anything Helix needs that the SDK can't provide is a
quality bug in the SDK.

[PASSPORT-STUB] verification matches Sentinel's — the canonical digest
is in `helios_allocator.service.auth` so the frontend can sign once and
hit either allocator.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from helios_allocator.runtime import (
    AllocatorEvent,
    AllocatorGoldsky,
    AllocatorLoop,
    AllocatorOnChain,
    AllocatorStore,
    LoopConfig,
)
from helios_allocator.service import (
    AllocationView,
    DashboardPayload,
    MetaStrategyPayload,
    MetaStrategySignatureError,
    NonceStore,
    StrategyDirectoryRow,
    verify_meta_strategy_signature,
)
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from helix.allocator import HelixAllocator


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="HELIX_", env_file=".env", extra="ignore")

    name: str = "Helios Helix"
    # Helix-lite ships at 600 bps so the side-by-side leaderboard shows a
    # real fee differential vs Sentinel's 400 bps. Same rationale tying it
    # to the allocator class default — both are kept in sync.
    fee_rate_bps: int = 600
    drawdown_check_interval_sec: int = 60
    rank_update_interval_sec: int = 300
    fee_check_interval_sec: int = 300
    operator_pk: str = Field(default="", validation_alias="HELIX_OPERATOR_PK")
    allocator_vault_address: str = Field(
        default="", validation_alias="HELIX_ALLOCATOR_VAULT_ADDRESS"
    )
    allocator_registry_address: str = Field(
        default="", validation_alias="HELIX_ALLOCATOR_REGISTRY_ADDRESS"
    )
    # Default port chosen to avoid the existing services on the same VPS:
    # sentinel=8001, reputation=8002, oracle=8003, prover=8004, bot=8005.
    http_port: int = 8006


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "helios-helix/0.1"})
    store = AllocatorStore()
    # [PASSPORT-STUB] replay-protection store; see Sentinel for the same wiring.
    nonce_store = NonceStore()
    allocator = HelixAllocator()
    goldsky = AllocatorGoldsky(
        endpoint=cfg.goldsky_endpoint, chain_id=cfg.kite_chain_id, client=http_client
    )
    onchain = AllocatorOnChain(
        rpc_url=cfg.kite_rpc_url,
        operator_pk=cfg.operator_pk,
        allocator_vault_address=cfg.allocator_vault_address,
        allocator_registry_address=cfg.allocator_registry_address,
        chain_id=cfg.kite_chain_id,
    )
    loop = AllocatorLoop(
        store=store,
        allocator=allocator,
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(
            drawdown_check_interval_sec=cfg.drawdown_check_interval_sec,
            rank_update_interval_sec=cfg.rank_update_interval_sec,
            fee_check_interval_sec=cfg.fee_check_interval_sec,
        ),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        loop.start()
        try:
            yield
        finally:
            await loop.stop()
            await http_client.aclose()

    router = _make_router(cfg, store, loop, onchain, goldsky, nonce_store)

    app = create_app(name="helix", settings=cfg, routers=[router])
    app.router.lifespan_context = _compose_lifespans(app.router.lifespan_context, lifespan)
    app.state.store = store  # type: ignore[attr-defined]
    app.state.loop = loop  # type: ignore[attr-defined]
    app.state.allocator = allocator  # type: ignore[attr-defined]
    app.state.onchain = onchain  # type: ignore[attr-defined]
    app.state.goldsky = goldsky  # type: ignore[attr-defined]
    return app


def _make_router(
    cfg: Settings,
    store: AllocatorStore,
    loop: AllocatorLoop,
    onchain: AllocatorOnChain,
    goldsky: AllocatorGoldsky,
    nonce_store: NonceStore,
) -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": cfg.name,
            "fee_rate_bps": cfg.fee_rate_bps,
            "scenario_mode": int(cfg.scenario_mode),
            "allocator_vault": cfg.allocator_vault_address,
            "live_chain_io": onchain.live,
            "candidates": len(loop.candidates),
            "users": len(store.all_users()),
        }

    @router.post("/users/{user}/meta-strategy")
    async def set_meta_strategy(user: str, payload: MetaStrategyPayload) -> dict[str, object]:
        if user.lower() != payload.user_address.lower():
            raise HTTPException(status_code=400, detail="path/body user mismatch")
        # [PASSPORT-STUB] — same canonical digest verifier as Sentinel
        # (`helios_allocator.service.auth`); a frontend can sign once and
        # post to either allocator. Nonce + valid_until checks close the
        # signature-replay hole called out in `docs/phase-3-review.md`.
        try:
            verify_meta_strategy_signature(payload, nonce_store=nonce_store)
        except MetaStrategySignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from None
        meta = payload.to_sdk_meta()
        store.upsert_user(meta)
        store.emit_event(
            AllocatorEvent(
                user_address=meta.user_address,
                kind="META_STRATEGY_SET",
                strategy_id=None,
                amount_usd=0,
                reason="meta-strategy signed",
                timestamp=int(time.time()),
            )
        )
        u = store.get_user(meta.user_address)
        return {
            "ok": True,
            "user": meta.user_address,
            "delegated_capital_usd": u.delegated_capital_usd if u else 0,
        }

    @router.get("/users/{user}/dashboard")
    async def dashboard(user: str) -> DashboardPayload:
        state = store.get_user(user)
        if state is None:
            raise HTTPException(status_code=404, detail=f"no meta-strategy for {user}")
        return _dashboard_for(state, cfg)

    @router.get("/strategies")
    async def list_strategies(
        cls: str | None = None,
        chain_id: int | None = None,
        min_reputation: float | None = None,
    ) -> list[StrategyDirectoryRow]:
        rows = await loop.directory()
        return _filter_directory(rows, cls=cls, chain_id=chain_id, min_reputation=min_reputation)

    @router.websocket("/users/{user}/events")
    async def user_events(ws: WebSocket, user: str) -> None:
        await ws.accept()
        q = store.subscribe(user)
        try:
            for e in store.recent_events(user, n=50):
                await ws.send_json(e.to_dict())
            while True:
                event = await q.get()
                await ws.send_json(event.to_dict())
        except WebSocketDisconnect:
            pass
        finally:
            store.unsubscribe(user, q)

    return router


def _dashboard_for(state, cfg: Settings) -> DashboardPayload:
    allocations = [
        AllocationView(
            strategy_id=a.strategy_id,
            chain_id=a.chain_id,
            declared_class=a.declared_class,
            capital_deployed_usd=a.capital_deployed_usd,
            high_water_mark_usd=a.high_water_mark_usd,
            current_nav_usd=a.nav_usd,
            drawdown_bps=a.drawdown_bps,
            defunded=a.defunded,
            last_rebalance_ts=a.last_rebalance_ts,
        )
        for a in state.allocations.values()
    ]
    active = [a for a in state.allocations.values() if not a.defunded]
    return DashboardPayload(
        user_address=state.meta.user_address,
        total_capital_usd=sum(a.capital_deployed_usd for a in active),
        total_nav_usd=sum(a.nav_usd for a in active),
        realized_pnl_usd=state.realized_pnl_usd,
        fees_paid_usd=state.fees_paid_usd,
        allocations=allocations,
        allocator_name=cfg.name,
        allocator_fee_rate_bps=cfg.fee_rate_bps,
    )


def _filter_directory(
    rows,
    *,
    cls: str | None,
    chain_id: int | None,
    min_reputation: float | None,
) -> list[StrategyDirectoryRow]:
    out: list[StrategyDirectoryRow] = []
    for r in rows:
        if cls and r.declared_class != cls:
            continue
        if chain_id is not None and r.chain_id != chain_id:
            continue
        rep = max(0.0, r.reputation_score_e4 / 10_000.0)
        if min_reputation is not None and rep < min_reputation:
            continue
        out.append(
            StrategyDirectoryRow(
                strategy_id=r.strategy_id,
                declared_class=r.declared_class,
                chain_id=r.chain_id,
                operator=r.operator,
                fee_rate_bps=r.fee_rate_bps,
                stake_amount_usd=r.stake_amount_usd,
                max_capacity_usd=r.max_capacity_usd,
                current_allocations_usd=r.current_allocations_usd,
                reputation_score=rep,
                realized_volatility_30d=0.0,
                sharpe_30d=0.0,
                max_drawdown_30d_bps=0,
            )
        )
    return out


def _compose_lifespans(outer, inner):
    @asynccontextmanager
    async def composed(app: FastAPI) -> AsyncIterator[None]:
        async with outer(app), inner(app):
            yield

    return composed
