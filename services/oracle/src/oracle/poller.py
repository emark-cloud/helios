"""Background poller — fetches each asset every `interval_sec` from the
configured chain of price sources, falling through on `SourceError`.

Owns no state of its own; pushes into `SnapshotStore`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence

import structlog

from oracle.sources.base import PriceSource, SourceError
from oracle.state import SnapshotStore

_log = structlog.get_logger(__name__)


class Poller:
    def __init__(
        self,
        store: SnapshotStore,
        sources: Sequence[PriceSource],
        assets: Sequence[str],
        interval_sec: int,
        on_snapshot: Callable[[str], object] | None = None,
    ) -> None:
        if not sources:
            raise ValueError("at least one source required")
        if not assets:
            raise ValueError("at least one asset required")
        self._store = store
        self._sources = list(sources)
        self._assets = list(assets)
        self._interval = max(1, interval_sec)
        self._on_snapshot = on_snapshot
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="oracle.poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def tick_once(self) -> None:
        """Run one poll across every (asset × source-fallback) pair. Used by tests."""
        for asset in self._assets:
            await self._poll_asset(asset)

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.tick_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def _poll_asset(self, asset: str) -> None:
        last_err: Exception | None = None
        for src in self._sources:
            try:
                quote = await src.fetch(asset)
            except SourceError as exc:
                last_err = exc
                _log.debug("oracle.source.fallthrough", source=src.name, asset=asset, err=str(exc))
                continue
            except Exception as exc:  # never let a misbehaving source kill the loop
                last_err = exc
                _log.warning(
                    "oracle.source.unexpected",
                    source=src.name,
                    asset=asset,
                    err=str(exc),
                    exc_info=True,
                )
                continue
            self._store.append(
                asset=asset,
                price_e18=quote.price_e18,
                timestamp_ms=quote.timestamp_ms,
                source=quote.source,
            )
            _log.info(
                "oracle.snapshot",
                asset=asset,
                source=quote.source,
                price_e18=quote.price_e18,
                ts_ms=quote.timestamp_ms,
            )
            if self._on_snapshot is not None:
                # Hook errors must never kill the poll loop — the snapshot
                # is already in the store; anchor commits are advisory.
                try:
                    self._on_snapshot(asset)
                except Exception as exc:
                    _log.warning("oracle.snapshot.hook_failed", asset=asset, err=str(exc))
            return
        _log.error(
            "oracle.snapshot.no_source",
            asset=asset,
            err=str(last_err) if last_err else "all sources rejected",
            exc_info=last_err is not None,
        )
