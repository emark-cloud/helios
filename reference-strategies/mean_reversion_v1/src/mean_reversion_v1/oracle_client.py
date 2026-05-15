"""Thin HTTP client for `services/oracle`.

The strategy polls `/v1/snapshots/recent?asset=…&n=…` once per bar to
build the `MarketSnapshot` it hands to `on_bar`. The same endpoint
returns the signed digests the witness builder hashes into the
oracle root. Pulling twice is wasteful, so the client returns both
shapes in one call.

In `SCENARIO_MODE=1` the oracle service replays the deterministic
scenario file — the strategy code doesn't branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from helios.types import MarketSnapshot


@dataclass(frozen=True, slots=True)
class SignedSnapshot:
    asset: str
    price_e18: int
    timestamp_ms: int
    source: str
    digest: bytes  # 32-byte digest the oracle signed (Poseidon BN254 element)
    signature: bytes  # 65-byte recoverable signature


@dataclass(frozen=True, slots=True)
class SnapshotBundle:
    market: MarketSnapshot
    signed: list[SignedSnapshot]
    chain_root: bytes  # Poseidon-chain over the included digests, oldest→newest


class OracleClient:
    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient | None = None,
        commit_token: str = "",
    ) -> None:
        if not endpoint:
            raise ValueError("oracle endpoint required")
        self._endpoint = endpoint.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._commit_token = commit_token

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_recent(self, asset: str, n: int) -> SnapshotBundle:
        if n < 1:
            raise ValueError("n must be >= 1")
        snaps = await self._fetch_recent_raw(asset, n)
        if not snaps:
            raise OracleEmptyError(f"oracle returned no snapshots for {asset}")
        # The oracle returns newest-first; reverse for the price array
        # so `MarketSnapshot.prices` is oldest→newest as the SDK expects.
        ordered = list(reversed(snaps))
        prices = [s.price_e18 / 1e18 for s in ordered]
        head_ts_ms = ordered[-1].timestamp_ms

        market = MarketSnapshot(
            asset=asset,
            timestamp=datetime.fromtimestamp(head_ts_ms / 1000, tz=UTC),
            prices=prices,
            bar_interval_sec=60,
        )
        chain_root = await self._fetch_chain_root(asset, n)
        return SnapshotBundle(market=market, signed=ordered, chain_root=chain_root)

    async def _fetch_recent_raw(self, asset: str, n: int) -> list[SignedSnapshot]:
        resp = await self._client.get(
            f"{self._endpoint}/v1/snapshots/recent",
            params={"asset": asset, "n": n},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        out: list[SignedSnapshot] = []
        for raw in body.get("snapshots") or []:
            out.append(
                SignedSnapshot(
                    asset=str(raw["asset"]),
                    price_e18=int(raw["price_e18"]),
                    timestamp_ms=int(raw["timestamp_ms"]),
                    source=str(raw.get("source", "")),
                    digest=_unhex(raw["digest"]),
                    signature=_unhex(raw["signature"]),
                )
            )
        return out

    async def request_commit(self, asset: str) -> dict[str, Any]:
        """Anchor a fresh price root for `asset` on-chain NOW
        (commit-on-demand). Called immediately before proving so the
        proof's `oracle_root` is ~0s old against StrategyVault's 180s
        freshness gate. Raises `OracleCommitError` on any non-200
        (endpoint disabled, bad/missing token, cold start, dry-run, or
        failed submit) — the runtime treats that as a safe skip, which
        is strictly better than submitting a proof that reverts
        `UnknownOracleRoot`/`OracleRootStale` on-chain."""
        headers = {"Authorization": f"Bearer {self._commit_token}"} if self._commit_token else {}
        resp = await self._client.post(
            f"{self._endpoint}/v1/anchor/commit",
            params={"asset": asset},
            headers=headers,
        )
        if resp.status_code != 200:
            try:
                detail = str(resp.json().get("detail", ""))
            except Exception:
                detail = resp.text
            raise OracleCommitError(f"anchor commit {resp.status_code}: {detail}")
        return resp.json()

    async def _fetch_chain_root(self, asset: str, n: int) -> bytes:
        resp = await self._client.get(
            f"{self._endpoint}/v1/snapshots/root",
            params={"asset": asset, "n": n},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        # Oracle returns `root` as a decimal BN254 field element string
        # (variable / often odd length) and `root_bytes32` as the
        # canonical 0x hex form. Hex form is what _unhex consumes.
        raw = body.get("root_bytes32") or body["root"]
        return _unhex(raw)


class OracleCommitError(RuntimeError):
    """`POST /v1/anchor/commit` did not return a mined commit.

    Raised on endpoint-disabled (token unset), auth failure, cold
    start, dry-run, or a failed on-chain submit. The runtime treats
    this as a safe skip of the current bar's trade.
    """


class OracleEmptyError(RuntimeError):
    """Oracle has no snapshots yet for the requested asset.

    The runtime treats this as a soft-skip — no signal can fire on an
    empty price history. Logged at INFO, not WARN.
    """


def _unhex(s: str) -> bytes:
    s = s[2:] if s.startswith("0x") else s
    return bytes.fromhex(s)
