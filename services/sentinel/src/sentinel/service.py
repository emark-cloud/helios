"""Sentinel allocator service composition.

Wires the decision loop, the in-memory store, the Goldsky client, and
the on-chain runner into a FastAPI app.

REST surface (`Helios.md §11.3`):
  * `POST /v1/users/{user}/meta-strategy` — accept a signed meta-strategy
  * `GET  /v1/users/{user}/dashboard`     — composite dashboard payload
  * `GET  /v1/strategies`                 — public directory with filters
  * `WS   /v1/users/{user}/events`        — per-user event stream

`POST /v1/users/{user}/meta-strategy` is the user's entry point. The
sigfield is stored verbatim — Phase 1 doesn't verify it (the user IS
the caller off the AA stack, [PASSPORT-STUB]); it does the same forward
preservation that `UserVault.setMetaStrategy` does.
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
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from sentinel.allocator import SentinelAllocator
from sentinel.auth import (
    MetaStrategySignatureError,
    NonceStore,
    WSSubscribeSignatureError,
    verify_meta_strategy_signature,
    verify_ws_subscribe_signature,
)
from sentinel.schemas import (
    AllocationView,
    DashboardPayload,
    MetaStrategyPayload,
    StrategyDirectoryRow,
)


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env", extra="ignore")

    name: str = "Helios Sentinel"
    fee_rate_bps: int = 400  # phase1-plan.md §"Setup", confirmed 2026-04-25
    drawdown_check_interval_sec: int = 60
    rank_update_interval_sec: int = 300
    fee_check_interval_sec: int = 300
    operator_pk: str = Field(default="", validation_alias="SENTINEL_OPERATOR_PK")
    allocator_vault_address: str = Field(
        default="", validation_alias="SENTINEL_ALLOCATOR_VAULT_ADDRESS"
    )
    allocator_registry_address: str = Field(
        default="", validation_alias="SENTINEL_ALLOCATOR_REGISTRY_ADDRESS"
    )
    http_port: int = 8001


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "helios-sentinel/0.1"})
    store = AllocatorStore()
    # [PASSPORT-STUB] replay-protection store; bounded by `valid_until`
    # eviction. Single-process state — fine for one PM2 worker, see
    # `docs/phase-3-review.md` for the multi-replica migration note.
    nonce_store = NonceStore()
    allocator = SentinelAllocator()
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

    app = create_app(name="sentinel", settings=cfg, routers=[router])
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
        # [PASSPORT-STUB] Verify the EOA personal_sign signature server-side.
        # Phase 4 swaps this for AA userOp verification at the EntryPoint —
        # see docs/kite-passport-notes.md §"Migration plan". Nonce + valid_until
        # checks in `verify_meta_strategy_signature` close the replay hole
        # called out in `docs/phase-3-review.md`.
        try:
            verify_meta_strategy_signature(payload, nonce_store=nonce_store)
        except MetaStrategySignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from None
        meta = payload.to_sdk_meta()
        store.upsert_user(meta)
        # Append an operational event so the activity rail (live and on
        # reconnect-replay) reflects that the user is delegated. Without
        # this the rail stays blank until the first allocation lands.
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
        # PR5 (item 21): read from the loop's cached directory instead of
        # firing a fresh Goldsky query on every dashboard load. The cache
        # refreshes on the same `rank_update_interval_sec` cadence the
        # decision loop already uses.
        rows = await loop.directory()
        return _filter_directory(rows, cls=cls, chain_id=chain_id, min_reputation=min_reputation)

    @router.websocket("/users/{user}/events")
    async def user_events(ws: WebSocket, user: str) -> None:
        # WS auth (HIGH #18 from `docs/phase-3-review.md`). The frontend
        # signs `ws_subscribe_digest(user, valid_until)` via personal_sign
        # right before opening the socket and passes the result on the
        # query string. We close with code 4401 ("application-level
        # unauthorized") instead of accepting and immediately closing —
        # that lets the client distinguish auth failure from network
        # noise without having to send a frame.
        try:
            valid_until = int(ws.query_params.get("valid_until", "0"))
        except ValueError:
            await ws.close(code=4401, reason="invalid valid_until")
            return
        signature = ws.query_params.get("signature", "")
        try:
            verify_ws_subscribe_signature(user, valid_until, signature)
        except WSSubscribeSignatureError as exc:
            # `reason` is shown in browser devtools; the message is
            # static enough to be safe (no signer-controlled echo).
            await ws.close(code=4401, reason=str(exc)[:120])
            return

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
            )
        )
    return out


def _compose_lifespans(outer, inner):
    @asynccontextmanager
    async def composed(app: FastAPI) -> AsyncIterator[None]:
        async with outer(app), inner(app):
            yield

    return composed
