"""ChainWatcher tests.

Two layers, mirroring `test_onchain.py`:

  1. **Decoding + emit** — feed pre-built log payloads through
     `_handle_logs` and assert the watcher translates them to the
     right `AllocatorEvent`s (or correctly suppresses them via the
     `(tx_hash, kind, strategy_id)` dedup ring).
  2. **Tick + checkpoint** — drive `tick_once` against a fake
     `eth.block_number` / `eth.get_logs` so we exercise the polling
     window walk without a real RPC.

Per `test_onchain.py`'s precedent, live RPC submission against anvil
is exercised end-to-end by `scripts/e2e-scenario.sh`. We don't add a
separate per-test anvil harness — that would duplicate the e2e
infrastructure for marginal extra confidence.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from eth_abi.abi import encode as abi_encode
from helios_allocator.runtime import AllocatorEvent, AllocatorStore
from helios_allocator.runtime.state import AllocationState, UserState
from helios_allocator.types import MetaStrategy
from sentinel.chain_watch import (
    ChainWatchConfig,
    ChainWatcher,
    WatchAddresses,
)
from web3 import Web3
from web3.datastructures import AttributeDict

# ── Fixtures ──────────────────────────────────────────────────────────

_USER_A = "0x" + "11" * 20
_USER_B = "0x" + "22" * 20
_STRATEGY = "0x" + "33" * 20
_STRATEGY_ALT = "0x" + "44" * 20
_ALLOCATOR_VAULT = "0x" + "55" * 20
_TRIGGERER = "0x" + "66" * 20
_TX_HASH = "0x" + "ab" * 32

_DEFAULT_META_KW = {
    "allowed_strategy_classes": ["momentum_v1"],
    "allowed_assets": ["WBTC"],
    "allowed_chains": [2368],
    "max_capital_usd": 100_000,
    "max_per_strategy_bps": 5_000,
    "max_strategies_count": 3,
    "drawdown_threshold_bps": 500,
    "max_fee_rate_bps": 1_000,
    "rebalance_cadence_sec": 3_600,
    "valid_until": 9_999_999_999,
    "bootstrap_share_bps": 1_000,
    "min_attested_trades": 50,
    "signature": "0x" + "00" * 65,
}


def _meta(addr: str) -> MetaStrategy:
    return MetaStrategy(user_address=addr, **_DEFAULT_META_KW)  # type: ignore[arg-type]


def _store_with_users(*addrs: str) -> AllocatorStore:
    s = AllocatorStore()
    for a in addrs:
        s.upsert_user(_meta(a))
    return s


def _alloc(strategy: str = _STRATEGY, *, defunded: bool = False) -> AllocationState:
    return AllocationState(
        strategy_id=strategy,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=10_000,
        defunded=defunded,
    )


def _addresses(*strategies: str) -> WatchAddresses:
    sids = strategies or (_STRATEGY,)
    return WatchAddresses(
        allocator_vault=Web3.to_checksum_address(_ALLOCATOR_VAULT),
        strategy_vaults=tuple(Web3.to_checksum_address(s) for s in sids),
    )


def _config(addresses: WatchAddresses, **overrides: Any) -> ChainWatchConfig:
    base = {
        "rpc_url": "http://localhost:65535",
        "chain_id": 2368,
        "addresses": addresses,
        "poll_interval_sec": 0.0,
    }
    base.update(overrides)
    return ChainWatchConfig(**base)  # type: ignore[arg-type]


def _watcher(
    *,
    store: AllocatorStore,
    addresses: WatchAddresses | None = None,
    web3_factory: Any | None = None,
    **cfg_overrides: Any,
) -> ChainWatcher:
    cfg = _config(addresses or _addresses(), **cfg_overrides)
    return ChainWatcher(
        store=store,
        config=cfg,
        web3_factory=web3_factory or Web3,
    )


# ── Log-builder helpers ───────────────────────────────────────────────


def _topic_for(signature: str) -> bytes:
    return bytes(Web3.keccak(text=signature))


def _addr_topic(addr: str) -> bytes:
    return bytes(12) + bytes.fromhex(addr.removeprefix("0x"))


def _make_log(
    *,
    address: str,
    topics: list[bytes],
    data: bytes,
    tx_hash: str = _TX_HASH,
    log_index: int = 0,
    block_number: int = 100,
) -> AttributeDict[str, Any]:
    return AttributeDict(
        {
            "address": Web3.to_checksum_address(address),
            "topics": [_HexBytes(t) for t in topics],
            "data": _HexBytes(data),
            "transactionHash": _HexBytes(bytes.fromhex(tx_hash.removeprefix("0x"))),
            "logIndex": log_index,
            "blockNumber": block_number,
            "blockHash": _HexBytes(bytes(32)),
            "transactionIndex": 0,
            "removed": False,
        }
    )


class _HexBytes(bytes):
    """Tiny replacement for `hexbytes.HexBytes` so we don't pull in the
    transitive dep just for tests."""

    def hex(self) -> str:  # type: ignore[override]
        return super().hex()


# ── Decoded-log builders for each watched event ───────────────────────


def _allocation_created_log(
    user: str = _USER_A,
    strategy: str = _STRATEGY,
    amount: int = 5_000,
    chain_id: int = 2368,
    *,
    address: str = _ALLOCATOR_VAULT,
    tx_hash: str = _TX_HASH,
) -> AttributeDict[str, Any]:
    return _make_log(
        address=address,
        topics=[
            _topic_for("AllocationCreated(address,address,uint256,uint32)"),
            _addr_topic(user),
            _addr_topic(strategy),
        ],
        data=abi_encode(["uint256", "uint32"], [amount, chain_id]),
        tx_hash=tx_hash,
    )


def _allocation_increased_log(
    user: str = _USER_A,
    strategy: str = _STRATEGY,
    delta: int = 1_500,
    *,
    tx_hash: str = _TX_HASH,
) -> AttributeDict[str, Any]:
    return _make_log(
        address=_ALLOCATOR_VAULT,
        topics=[
            _topic_for("AllocationIncreased(address,address,uint256)"),
            _addr_topic(user),
            _addr_topic(strategy),
        ],
        data=abi_encode(["uint256"], [delta]),
        tx_hash=tx_hash,
    )


def _strategy_defunded_log(
    user: str = _USER_A,
    strategy: str = _STRATEGY,
    reason: str = "DRAWDOWN_BREACH",
    triggered_by: str = _TRIGGERER,
    *,
    tx_hash: str = _TX_HASH,
) -> AttributeDict[str, Any]:
    return _make_log(
        address=_ALLOCATOR_VAULT,
        topics=[
            _topic_for("StrategyDefunded(address,address,string,address)"),
            _addr_topic(user),
            _addr_topic(strategy),
            _addr_topic(triggered_by),
        ],
        data=abi_encode(["string"], [reason]),
        tx_hash=tx_hash,
    )


def _defund_observed_log(
    user: str = _USER_A,
    strategy: str = _STRATEGY,
    triggerer: str = _TRIGGERER,
    breach_count: int = 2,
    drawdown_bps: int = 1_500,
    bond_amount: int = 50_000_000,
    *,
    tx_hash: str = _TX_HASH,
) -> AttributeDict[str, Any]:
    return _make_log(
        address=_ALLOCATOR_VAULT,
        topics=[
            _topic_for("DefundObserved(address,address,address,uint8,uint256,uint256)"),
            _addr_topic(user),
            _addr_topic(strategy),
            _addr_topic(triggerer),
        ],
        data=abi_encode(
            ["uint8", "uint256", "uint256"],
            [breach_count, drawdown_bps, bond_amount],
        ),
        tx_hash=tx_hash,
    )


def _defund_finalized_log(
    user: str = _USER_A,
    strategy: str = _STRATEGY,
    triggerer: str = _TRIGGERER,
    refunded: int = 0,
    reward: int = 100_000_000,
    slashed_to_user: int = 0,
    *,
    tx_hash: str = _TX_HASH,
) -> AttributeDict[str, Any]:
    return _make_log(
        address=_ALLOCATOR_VAULT,
        topics=[
            _topic_for("DefundFinalized(address,address,address,uint256,uint256,uint256)"),
            _addr_topic(user),
            _addr_topic(strategy),
        ],
        data=abi_encode(
            ["address", "uint256", "uint256", "uint256"],
            [Web3.to_checksum_address(triggerer), refunded, reward, slashed_to_user],
        ),
        tx_hash=tx_hash,
    )


def _nav_divergence_log(
    strategy: str = _STRATEGY,
    signed_nav: int = 90_000,
    marked_floor: int = 100_000,
    snapshot_nonce: int = 7,
    *,
    address: str | None = None,
    tx_hash: str = _TX_HASH,
) -> AttributeDict[str, Any]:
    return _make_log(
        address=address or strategy,
        topics=[
            _topic_for("NavDivergenceObserved(address,uint256,uint256,uint64)"),
            _addr_topic(strategy),
        ],
        data=abi_encode(
            ["uint256", "uint256", "uint64"],
            [signed_nav, marked_floor, snapshot_nonce],
        ),
        tx_hash=tx_hash,
    )


# ── Decoding + emit tests ─────────────────────────────────────────────


def test_allocation_created_emits_to_user() -> None:
    store = _store_with_users(_USER_A)
    w = _watcher(store=store)
    emitted = w._handle_logs([_allocation_created_log()])
    assert emitted == 1
    events = store.recent_events(_USER_A)
    assert [e.kind for e in events] == ["ALLOCATION_CREATED"]
    e = events[-1]
    assert e.strategy_id == _STRATEGY.lower()
    assert e.amount_usd == 5_000
    assert e.tx_hash.lower() == _TX_HASH.lower()


def test_allocation_increased_carries_delta() -> None:
    store = _store_with_users(_USER_A)
    w = _watcher(store=store)
    w._handle_logs([_allocation_increased_log(delta=2_500)])
    events = store.recent_events(_USER_A)
    assert events[-1].kind == "ALLOCATION_INCREASED"
    assert events[-1].amount_usd == 2_500


def test_strategy_defunded_carries_reason() -> None:
    store = _store_with_users(_USER_A)
    w = _watcher(store=store)
    w._handle_logs([_strategy_defunded_log(reason="DRAWDOWN_BREACH")])
    events = store.recent_events(_USER_A)
    assert events[-1].kind == "STRATEGY_DEFUNDED"
    assert events[-1].reason == "DRAWDOWN_BREACH"


def test_defund_observed_emits_with_breach_count_in_reason() -> None:
    store = _store_with_users(_USER_A)
    w = _watcher(store=store)
    w._handle_logs([_defund_observed_log(breach_count=3, drawdown_bps=1_750)])
    events = store.recent_events(_USER_A)
    assert events[-1].kind == "DEFUND_TRIGGERED"
    assert events[-1].reason == "BREACH_3"
    # amount carries the observed drawdown in bps so the rail can render
    # without a second lookup.
    assert events[-1].amount_usd == 1_750


def test_defund_finalized_distinguishes_slash_vs_refund() -> None:
    store = _store_with_users(_USER_A)
    w = _watcher(store=store)
    # Slash-to-user path.
    w._handle_logs([_defund_finalized_log(slashed_to_user=10_000_000, reward=0, tx_hash=_TX_HASH)])
    alt_tx = "0x" + "cd" * 32
    # Refund path (different tx — same kind/strategy would otherwise dedup).
    w._handle_logs([_defund_finalized_log(slashed_to_user=0, reward=20_000_000, tx_hash=alt_tx)])
    events = store.recent_events(_USER_A)
    kinds = [e.kind for e in events]
    reasons = [e.reason for e in events]
    assert kinds.count("DEFUND_FINALIZED") == 2
    assert "SLASHED_TO_USER" in reasons
    assert "REFUNDED" in reasons


def test_nav_divergence_fans_out_to_users_with_live_alloc() -> None:
    store = _store_with_users(_USER_A, _USER_B)
    user_a = store.get_user(_USER_A)
    user_b = store.get_user(_USER_B)
    assert user_a is not None and user_b is not None
    user_a.allocations[_STRATEGY] = _alloc(strategy=_STRATEGY)
    user_b.allocations[_STRATEGY] = _alloc(strategy=_STRATEGY, defunded=True)
    w = _watcher(store=store)
    w._handle_logs([_nav_divergence_log()])
    # User A has a live alloc → emitted; user B is defunded → skipped.
    a_events = store.recent_events(_USER_A)
    b_events = store.recent_events(_USER_B)
    assert any(e.kind == "NAV_DIVERGENCE" for e in a_events)
    assert all(e.kind != "NAV_DIVERGENCE" for e in b_events)


def test_dedup_skips_loop_emit_with_same_tx() -> None:
    store = _store_with_users(_USER_A)
    # Loop emits first with the same tx_hash a chain log will carry.
    store.emit_event(
        AllocatorEvent(
            user_address=_USER_A,
            kind="STRATEGY_DEFUNDED",
            strategy_id=_STRATEGY.lower(),
            amount_usd=10_000,
            reason="DRAWDOWN_BREACH",
            timestamp=1,
            tx_hash=_TX_HASH,
        )
    )
    pre = len(store.recent_events(_USER_A))
    w = _watcher(store=store)
    w._handle_logs([_strategy_defunded_log()])
    # No additional event — the dedup ring caught the duplicate.
    assert len(store.recent_events(_USER_A)) == pre


def test_unknown_user_drops_event() -> None:
    store = AllocatorStore()
    w = _watcher(store=store)
    emitted = w._handle_logs([_allocation_created_log()])
    assert emitted == 0
    assert store.recent_events(_USER_A) == []


def test_log_from_random_address_ignored() -> None:
    store = _store_with_users(_USER_A)
    w = _watcher(store=store)
    rogue = _allocation_created_log(address="0x" + "ee" * 20)
    emitted = w._handle_logs([rogue])
    assert emitted == 0
    assert store.recent_events(_USER_A) == []


def test_nav_divergence_from_unwatched_strategy_address_ignored() -> None:
    store = _store_with_users(_USER_A)
    user = store.get_user(_USER_A)
    assert user is not None
    user.allocations[_STRATEGY] = _alloc(strategy=_STRATEGY)
    # Watcher only tracks _STRATEGY; same topic emitted from
    # _STRATEGY_ALT (not in addresses) must be ignored, otherwise an
    # operator deploying a fake StrategyVault could spam the rail.
    w = _watcher(store=store, addresses=_addresses(_STRATEGY))
    log = _nav_divergence_log(address=_STRATEGY_ALT)
    emitted = w._handle_logs([log])
    assert emitted == 0


# ── Tick + checkpoint tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_tick_seeds_checkpoint_at_latest() -> None:
    store = _store_with_users(_USER_A)
    fake = _FakeWeb3(latest=1_000)
    w = _watcher(store=store, web3_factory=lambda: fake)
    emitted = await w.tick_once()
    assert emitted == 0
    assert w.last_scanned_block == 1_000
    assert fake.get_logs_calls == []  # nothing scanned on first tick


@pytest.mark.asyncio
async def test_tick_scans_window_and_advances_checkpoint() -> None:
    store = _store_with_users(_USER_A)
    fake = _FakeWeb3(latest=200)
    w = _watcher(store=store, web3_factory=lambda: fake)
    # Seed the checkpoint to a known starting block.
    await w.tick_once()
    fake.latest = 350
    fake.queue_logs([_allocation_created_log(amount=7_500)])
    emitted = await w.tick_once()
    assert emitted == 1
    # Scanned [201, 350] in one window (well under _MAX_LOGS_RANGE).
    assert fake.get_logs_calls[-1]["fromBlock"] == 201
    assert fake.get_logs_calls[-1]["toBlock"] == 350
    assert w.last_scanned_block == 350
    e = store.recent_events(_USER_A)[-1]
    assert e.amount_usd == 7_500


@pytest.mark.asyncio
async def test_checkpoint_persists_to_disk(tmp_path: Path) -> None:
    cp_path = tmp_path / "ck.json"
    store = _store_with_users(_USER_A)
    fake = _FakeWeb3(latest=10_000)
    # Flush every tick — config default is 4 ticks. Drive enough ticks
    # to trigger a flush, then reload from disk.
    w = _watcher(
        store=store,
        web3_factory=lambda: fake,
        checkpoint_path=cp_path,
    )
    # First tick seeds the checkpoint without scanning; each
    # subsequent tick increments `_Checkpoint.flushed`. The flush
    # threshold is 4 successful scan ticks → drive 5 total.
    for _ in range(5):
        fake.latest += 5
        await w.tick_once()
    assert cp_path.exists()
    body = json.loads(cp_path.read_text())
    assert body["last_scanned_block"] == w.last_scanned_block

    # Restart: a fresh watcher with the same path resumes from the file.
    fake2 = _FakeWeb3(latest=w.last_scanned_block + 100)
    fake2.queue_logs([_allocation_created_log(amount=999)])
    w2 = _watcher(
        store=store,
        web3_factory=lambda: fake2,
        checkpoint_path=cp_path,
    )
    emitted = await w2.tick_once()
    assert emitted == 1
    # Resumed from the persisted block + 1, not from `latest`.
    assert fake2.get_logs_calls[0]["fromBlock"] == w.last_scanned_block + 1


@pytest.mark.asyncio
async def test_stub_mode_tick_is_noop() -> None:
    """Empty rpc_url → live=False → tick is a no-op even if logs queued."""
    store = _store_with_users(_USER_A)
    cfg = ChainWatchConfig(
        rpc_url="",
        chain_id=2368,
        addresses=WatchAddresses(allocator_vault="", strategy_vaults=()),
    )
    w = ChainWatcher(store=store, config=cfg)
    assert w.live is False
    assert await w.tick_once() == 0


# ── Fake Web3 ─────────────────────────────────────────────────────────


class _FakeEth:
    def __init__(self) -> None:
        self.block_number_value = 0
        self._log_queue: list[list[Any]] = []
        self.get_logs_calls: list[dict[str, Any]] = []
        self._real = Web3()  # used only for `eth.contract` decoding

    @property
    def block_number(self) -> int:
        return self.block_number_value

    def get_logs(self, params: dict[str, Any]) -> list[Any]:
        self.get_logs_calls.append(params)
        if self._log_queue:
            return self._log_queue.pop(0)
        return []

    def contract(self, *args: Any, **kwargs: Any) -> Any:
        return self._real.eth.contract(*args, **kwargs)


class _FakeWeb3:
    """Minimal Web3 stand-in for the watcher's needs."""

    def __init__(self, latest: int = 0) -> None:
        self.eth = _FakeEth()
        self.eth.block_number_value = latest

    @property
    def latest(self) -> int:
        return self.eth.block_number_value

    @latest.setter
    def latest(self, v: int) -> None:
        self.eth.block_number_value = v

    @property
    def get_logs_calls(self) -> list[dict[str, Any]]:
        return self.eth.get_logs_calls

    def queue_logs(self, logs: list[Any]) -> None:
        self.eth._log_queue.append(logs)


# ── Misc ──────────────────────────────────────────────────────────────


def test_to_dict_includes_tx_hash_for_chain_events() -> None:
    """Frontend dedups across reconnects on the wire — the event
    payload must include `tx_hash` so the rail's reconnect-replay can
    skip duplicates that landed before the socket dropped."""
    store = _store_with_users(_USER_A)
    w = _watcher(store=store)
    w._handle_logs([_allocation_created_log()])
    payload = store.recent_events(_USER_A)[-1].to_dict()
    assert payload["tx_hash"] == _TX_HASH


def test_watch_addresses_from_deployments_picks_strategy_vaults() -> None:
    addrs = WatchAddresses.from_deployments(
        {
            "allocatorVault": _ALLOCATOR_VAULT,
            "strategyVaultMomentum": _STRATEGY,
            "strategyVaultMeanReversionVariant3": _STRATEGY_ALT,
            "userVault": "0x" + "99" * 20,  # ignored
            "swapRouter": "0x" + "88" * 20,  # ignored
        }
    )
    assert addrs.allocator_vault.lower() == _ALLOCATOR_VAULT.lower()
    assert {a.lower() for a in addrs.strategy_vaults} == {
        _STRATEGY.lower(),
        _STRATEGY_ALT.lower(),
    }


# Touch unused imports so the linter doesn't strip them — these are
# kept for readability of future test additions.
_ = (asyncio, time, MagicMock, UserState)
