"""Sentinel allocator service composition.

Wires the decision loop, the in-memory store, the Goldsky client, and
the on-chain runner into a FastAPI app.

REST surface (`Helios.md §11.3`):
  * `POST /v1/users/{user}/meta-strategy` — accept a signed meta-strategy
  * `GET  /v1/users/{user}/dashboard`     — composite dashboard payload
  * `GET  /v1/strategies`                 — public directory with filters
  * `WS   /v1/users/{user}/events`        — per-user event stream

`POST /v1/users/{user}/meta-strategy` is the user's entry point.
Sentinel verifies the EIP-191 signature for `auth: "eip191"` payloads
and trusts the on-chain userOp for `auth: "passport"` payloads (Phase
4 WS-FE-1) — both paths still enforce the `(user, nonce)` /
`valid_until` replay window via `verify_meta_strategy_signature`.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

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
from helios_allocator.runtime.goldsky import MultiChainAllocatorGoldsky, _normalise_class
from helios_allocator.runtime.state import UserState
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
from sentinel.chain_watch import ChainWatchConfig, ChainWatcher, WatchAddresses
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
    # UserVault proxy. When unset the loop's per-tick balance refresh
    # returns None and `delegated_capital_usd` stays at whatever the
    # POST or a test seeded — i.e. zero in production, so leave this
    # set to skip the gate on `if user.delegated_capital_usd <= 0`.
    user_vault_address: str = Field(default="", validation_alias="SENTINEL_USER_VAULT_ADDRESS")
    http_port: int = 8001
    # Chain-watcher (WS-SVC-1). Comma-separated list of StrategyVault
    # proxies whose `NavDivergenceObserved` logs the watcher fans out
    # to subscribed users. Defaults to empty so test/dry-run boots
    # don't require a real deployment file. The poll cadence matches
    # Kite's ~3s block time; tests override to drive `tick_once`
    # directly. Checkpoint persistence path is optional — when unset
    # the watcher restarts at `latest`, which is fine for the
    # dashboard rail (it does not replay historical events).
    chain_watch_strategy_vaults: str = Field(
        default="", validation_alias="SENTINEL_CHAIN_WATCH_STRATEGY_VAULTS"
    )
    chain_watch_poll_interval_sec: float = Field(
        default=3.0, validation_alias="SENTINEL_CHAIN_WATCH_POLL_INTERVAL_SEC"
    )
    chain_watch_checkpoint_path: str = Field(
        default="", validation_alias="SENTINEL_CHAIN_WATCH_CHECKPOINT_PATH"
    )
    # CXR-4 (2026-05-13) — per-chain Goldsky endpoints for §12.1 venue
    # routing. When at least one of these is set, Sentinel fans out
    # `fetch_directory()` across (Kite, Base, Arb) and surfaces every
    # chain's strategies in the candidate set + `/v1/strategies`. The
    # loop then defers any allocation whose target chain ≠
    # `kite_chain_id` (emits `CROSS_CHAIN_ALLOCATION_DEFERRED` instead
    # of submitting `allocateToStrategy` on Kite's vault, which would
    # revert `StrategyNotRegistered`). Once CXR-0a/0b lands on-chain
    # the loop flips to real cross-chain submission. Both blank →
    # Sentinel behaves exactly as before (Kite-only directory).
    goldsky_endpoint_base: str = Field(default="", validation_alias="GOLDSKY_ENDPOINT_BASE")
    goldsky_endpoint_arbitrum: str = Field(default="", validation_alias="GOLDSKY_ENDPOINT_ARBITRUM")
    # Chain ids for the per-chain endpoints above. Defaults match the
    # CXR-3 testnet deployment (Base Sepolia / Arbitrum Sepolia). Live
    # mainnet promotion is a stretch; if exercised, override both.
    base_chain_id: int = Field(default=84_532, validation_alias="BASE_SEPOLIA_CHAIN_ID")
    arbitrum_chain_id: int = Field(default=421_614, validation_alias="ARBITRUM_SEPOLIA_CHAIN_ID")
    # CXR-0c (2026-05-14) — live remote-allocation wiring. The
    # AllocatorVault on Kite is on the CXR-0c impl (per-EID
    # destinationReceiver). Setting `kite_oft_adapter_address` flips
    # the loop from defer-mode to live OFT.send; the LZ EIDs below
    # tell the runner which dstEid to target per supported chain. All
    # three blank → loop falls back to `CROSS_CHAIN_ALLOCATION_DEFERRED`.
    kite_oft_adapter_address: str = Field(
        default="", validation_alias="SENTINEL_KITE_OFT_ADAPTER_ADDRESS"
    )
    # v1 master kill-switch for live cross-chain *capital* movement.
    # Default False: v1 ships with cross-chain capital flow OFF — the LZ
    # V2 executor fee (~1–1.2 KITE per OFT.send, fixed-cost regardless of
    # payload) makes per-rebalance bridging impractical on testnet. With
    # this False the loop never attempts the live send even if the OFT
    # adapter above is wired; every remote op becomes a zero-cost
    # `CROSS_CHAIN_ALLOCATION_DEFERRED` event. This is a deliberate v1
    # product decision — a practical cross-chain capital design is a
    # documented v2 item (docs/cross-chain-cost-roadmap.md §"v2").
    # Cross-chain reputation propagation is unaffected and is a separate
    # KITE-free path: originates on Base/Arb only (no-op on Kite), LZ fee
    # paid in free Base/Arb Sepolia testnet ETH (~1e-4 ETH/msg, batched +
    # low-cadence), never the scarce KITE the capital OFT.send burned.
    # Set true ONLY for v2 work / live-path testing.
    cross_chain_capital_enabled: bool = Field(
        default=False, validation_alias="SENTINEL_CROSS_CHAIN_CAPITAL_ENABLED"
    )
    base_lz_eid: int = Field(default=40_245, validation_alias="BASE_LZ_EID")
    arbitrum_lz_eid: int = Field(default=40_231, validation_alias="ARBITRUM_LZ_EID")
    # Cross-chain cost Tier 1 — gates that suppress LZ V2 send waste.
    # `min_cross_chain_alloc_usd_wei` skips sub-threshold dust deltas
    # (default $10 ≈ 10e18 on Kite's 18-dec canonical scale); the next
    # tick re-evaluates the cumulative delta. `cross_chain_flush_cadence_sec`
    # enforces a per-(user, strategyId) cooldown between LZ V2 sends so
    # the 60s drawdown-tick cadence doesn't fire a fresh ~1 KITE send
    # on every cycle when the target oscillates. Set either to 0 to
    # disable. See `docs/cross-chain-cost-roadmap.md` for the cost shape
    # these levers attack.
    min_cross_chain_alloc_usd_wei: int = Field(
        default=10 * 10**18,
        validation_alias="SENTINEL_MIN_CROSS_CHAIN_ALLOC_USD_WEI",
    )
    cross_chain_flush_cadence_sec: int = Field(
        default=300,
        validation_alias="SENTINEL_CROSS_CHAIN_FLUSH_CADENCE_SEC",
    )
    # Local (same-chain) anti-dust-churn floor. An allocate→defund
    # round-trip costs ~10 bps swap spread + NAV float-clamp rounding;
    # below this |delta| the move destroys more value than it moves, so
    # the op is skipped and the capital stays put. This is what stops
    # the cold-start RANK_DROP flap from bleeding a meta-strategy user's
    # principal down to dust (observed live 2026-05-15). Default 1e15
    # wei = 0.001 mUSDC on Kite's 18-dec canonical scale — ~3 orders of
    # magnitude above observed dust, ~3 below any real allocation. 0
    # disables (tests / scenario mode).
    min_local_alloc_usd_wei: int = Field(
        default=10**15,
        validation_alias="SENTINEL_MIN_LOCAL_ALLOC_USD_WEI",
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()  # type: ignore[call-arg]

    http_client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "helios-sentinel/0.1"})
    store = AllocatorStore()
    # Replay-protection store; bounded by `valid_until` eviction.
    # Single-process state — fine for one PM2 worker, see
    # `docs/phase-3-review.md` for the multi-replica migration note.
    nonce_store = NonceStore()
    allocator = SentinelAllocator()
    goldsky = _build_goldsky(cfg, http_client)
    onchain = AllocatorOnChain(
        rpc_url=cfg.kite_rpc_url,
        operator_pk=cfg.operator_pk,
        allocator_vault_address=cfg.allocator_vault_address,
        allocator_registry_address=cfg.allocator_registry_address,
        chain_id=cfg.kite_chain_id,
        user_vault_address=cfg.user_vault_address,
        oft_adapter_address=cfg.kite_oft_adapter_address,
        remote_chain_eids={
            cfg.base_chain_id: cfg.base_lz_eid,
            cfg.arbitrum_chain_id: cfg.arbitrum_lz_eid,
        },
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
            cross_chain_capital_enabled=cfg.cross_chain_capital_enabled,
            min_cross_chain_alloc_usd_wei=cfg.min_cross_chain_alloc_usd_wei,
            cross_chain_flush_cadence_sec=cfg.cross_chain_flush_cadence_sec,
            min_local_alloc_usd_wei=cfg.min_local_alloc_usd_wei,
        ),
    )

    chain_watcher = _build_chain_watcher(cfg, store, loop)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        loop.start()
        chain_watcher.start()
        try:
            yield
        finally:
            await chain_watcher.stop()
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
    app.state.chain_watcher = chain_watcher  # type: ignore[attr-defined]
    return app


def _build_goldsky(
    cfg: Settings,
    http_client: httpx.AsyncClient,
) -> AllocatorGoldsky | MultiChainAllocatorGoldsky:
    """Pick the right Goldsky shape from configured endpoints.

    Kite-only (the default before CXR-4): return the original
    `AllocatorGoldsky` so the loop behaves byte-for-byte the same in
    production until the per-chain endpoints get filled in.

    At least one of `GOLDSKY_ENDPOINT_BASE` / `GOLDSKY_ENDPOINT_ARBITRUM`
    set: return a `MultiChainAllocatorGoldsky` that fans out across all
    configured chains. The Kite endpoint is always included (anchor
    chain), then the optional Base + Arbitrum endpoints. Empty entries
    are dropped by `MultiChainAllocatorGoldsky.from_endpoints` so a
    partial fan-out (e.g. Base configured but Arb not yet) works.
    """
    remote_endpoints = (cfg.goldsky_endpoint_base, cfg.goldsky_endpoint_arbitrum)
    if not any(remote_endpoints):
        return AllocatorGoldsky(
            endpoint=cfg.goldsky_endpoint,
            chain_id=cfg.kite_chain_id,
            client=http_client,
        )
    return MultiChainAllocatorGoldsky.from_endpoints(
        {
            cfg.kite_chain_id: cfg.goldsky_endpoint,
            cfg.base_chain_id: cfg.goldsky_endpoint_base,
            cfg.arbitrum_chain_id: cfg.goldsky_endpoint_arbitrum,
        },
        client=http_client,
    )


def _build_chain_watcher(cfg: Settings, store, loop: AllocatorLoop) -> ChainWatcher:
    """Compose a `ChainWatcher` from environment-driven settings.

    `SENTINEL_CHAIN_WATCH_STRATEGY_VAULTS` is now a *static floor*, not
    the authoritative set: the watcher unions it with `loop`'s live
    Goldsky `active` directory each scan, so a newly deployed strategy
    is observed without any env edit and a retired one drops off once
    it leaves the directory (the floor still pins anything an operator
    lists explicitly, and survives a directory blip). Leave the env
    empty to run purely dynamic.

    Stub mode kicks in whenever `kite_rpc_url` or `allocator_vault_address`
    is empty — the watcher's `live` property goes False and `start()`
    becomes a no-op, so test/dry-run boots don't need a live RPC.
    """
    strategy_vaults = tuple(
        s.strip() for s in cfg.chain_watch_strategy_vaults.split(",") if s.strip()
    )
    addresses = WatchAddresses(
        allocator_vault=cfg.allocator_vault_address,
        strategy_vaults=strategy_vaults,
    )
    checkpoint_path = (
        Path(cfg.chain_watch_checkpoint_path) if cfg.chain_watch_checkpoint_path else None
    )
    return ChainWatcher(
        store=store,
        config=ChainWatchConfig(
            rpc_url=cfg.kite_rpc_url,
            chain_id=cfg.kite_chain_id,
            addresses=addresses,
            poll_interval_sec=cfg.chain_watch_poll_interval_sec,
            checkpoint_path=checkpoint_path,
        ),
        strategy_vaults_provider=lambda: loop.watched_strategy_ids,
    )


def _make_router(
    cfg: Settings,
    store: AllocatorStore,
    loop: AllocatorLoop,
    onchain: AllocatorOnChain,
    goldsky: AllocatorGoldsky | MultiChainAllocatorGoldsky,
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
        # Verify per `payload.auth`: EIP-191 recovery for legacy/dev,
        # nonce + valid_until enforcement for Passport (the userOp at
        # the EntryPoint is the user's on-chain authorization there).
        # Both paths still close the replay hole called out in
        # `docs/phase-3-review.md`.
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
            state = await _rehydrate_from_chain(user, store, onchain, loop)
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


# Sentinel keeps every USD-named field as raw 18-decimal base-asset units
# (mUSDC has 18 decimals on Kite testnet — see `87e7cab`). Allocator math,
# `allocateToStrategy(amount)` calls, and the on-chain `capitalDeployed`
# accumulator all run in wei so they round-trip cleanly. The dashboard
# payload, by contrast, is a *display* surface — the `_usd` fields there
# are integer USD as the frontend formatter expects. Scale at the boundary
# so the loop's wei-native math is unchanged.
_BASE_ASSET_DECIMALS = 18
_BASE_ASSET_SCALE = 10**_BASE_ASSET_DECIMALS


def _to_usd(wei: int) -> int:
    return int(wei) // _BASE_ASSET_SCALE


async def _rehydrate_from_chain(
    user: str,
    store: AllocatorStore,
    onchain: AllocatorOnChain,
    loop: AllocatorLoop,
) -> UserState | None:
    """Rebuild a user's runtime state from chain after a store wipe.

    The store is in-process and is lost on a Sentinel restart, but the
    on-chain UserVault still holds the user's signed meta-strategy +
    live delegation and the AllocatorVault still holds their deployed
    positions. Rehydrate from chain rather than 404'ing a delegation
    that is still active — the on-chain meta IS the user's
    authorization, so this needs no re-signature. Self-heals every
    onboarded user on their first post-restart dashboard hit and
    re-arms the allocator loop (which skips users absent from the
    store). Returns None when there is genuinely no on-chain meta (a
    real 404).
    """
    meta = await onchain.read_user_meta_strategy_async(user)
    if meta is None:
        return None
    store.upsert_user(meta)
    # Restoring the meta tells us *what the user authorized*; it doesn't
    # tell us *where their capital currently is*. Without this, every
    # allocation row reads 0 capital until the next cadence-gated
    # rebalance happens to rewrite the in-memory mirror (observed live
    # on 0xF235F71…: ~999 mUSDC deployed on-chain, dashboard showing
    # $0). Reconstruct the live positions from
    # `AllocatorVault.allocationOf` so the dashboard is correct on the
    # first post-restart hit. Only same-chain (Kite) strategies are
    # queryable here — the canonical AllocatorVault doesn't hold
    # cross-chain positions; the loop's multi-chain mirror handles those.
    directory = await loop.directory()
    local_rows = [r for r in directory if r.chain_id in (0, onchain.chain_id)]
    rebuilt = await onchain.read_user_allocations_async(
        meta.user_address, [r.strategy_id for r in local_rows]
    )
    if rebuilt:
        # Directory rows carry the raw on-chain `declaredClass` bytes32
        # (unlike candidates, which `goldsky.to_candidate` already
        # normalises). Run it through the same reverse map so the
        # dashboard shows "momentum_v1", not a 0x… Poseidon id.
        class_by_id = {r.strategy_id: _normalise_class(r.declared_class) for r in local_rows}
        for a in rebuilt:
            a.declared_class = class_by_id.get(a.strategy_id, "")
        store.replace_allocations(meta.user_address, rebuilt)
    store.emit_event(
        AllocatorEvent(
            user_address=meta.user_address,
            kind="META_STRATEGY_SET",
            strategy_id=None,
            amount_usd=0,
            reason="rehydrated from on-chain UserVault",
            timestamp=int(time.time()),
        )
    )
    return store.get_user(user)


def _allocation_view(a) -> AllocationView:
    # A defunded allocation has had its principal swept back to the
    # user's liquid AllocatorVault balance (verified live on
    # 0xF235F71…: on defund `on_chain_deployed` 999→0, liquid balance
    # rose by the same amount). The loop's defund path only flips
    # `defunded=True` — it never zeroes `capital_deployed_usd` /
    # `nav_usd`, so the stale pre-defund figures linger in the store.
    # The frontend already ticks the Capital column to $0 for a
    # defunded row (DESIGN §10.2 auto-defund cascade) but renders NAV
    # straight from this payload, so a closed position showed $0
    # capital next to a phantom NAV ("capital and NAV don't tally").
    # A closed position holds nothing for this user: report 0 across
    # the money fields so every row is internally consistent.
    if a.defunded:
        return AllocationView(
            strategy_id=a.strategy_id,
            chain_id=a.chain_id,
            declared_class=a.declared_class,
            capital_deployed_usd=0,
            high_water_mark_usd=0,
            current_nav_usd=0,
            drawdown_bps=0,
            defunded=True,
            last_rebalance_ts=a.last_rebalance_ts,
        )
    return AllocationView(
        strategy_id=a.strategy_id,
        chain_id=a.chain_id,
        declared_class=a.declared_class,
        capital_deployed_usd=_to_usd(a.capital_deployed_usd),
        high_water_mark_usd=_to_usd(a.high_water_mark_usd),
        current_nav_usd=_to_usd(a.nav_usd),
        drawdown_bps=a.drawdown_bps,
        defunded=False,
        last_rebalance_ts=a.last_rebalance_ts,
    )


def _dashboard_for(state, cfg: Settings) -> DashboardPayload:
    allocations = [_allocation_view(a) for a in state.allocations.values()]
    active = [a for a in state.allocations.values() if not a.defunded]
    return DashboardPayload(
        user_address=state.meta.user_address,
        total_capital_usd=_to_usd(sum(a.capital_deployed_usd for a in active)),
        total_nav_usd=_to_usd(sum(a.nav_usd for a in active)),
        realized_pnl_usd=_to_usd(state.realized_pnl_usd),
        fees_paid_usd=_to_usd(state.fees_paid_usd),
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
