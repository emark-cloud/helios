"""HTTP client for `services/oracle`'s yield endpoints.

Polls `/v1/yield/recent?market_id=…&n=…` and `/v1/yield/markets`. The
strategy reconstructs the yield Merkle tree client-side from the
returned `(market_id, apy_bps_e6)` pairs (the oracle does not surface
leaves directly; Phase 5 may add `/v1/yield/leaves` to skip the
reconstruction).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from yield_rotation_v1.types import YieldTick


@dataclass(frozen=True, slots=True)
class SignedYieldSnapshot:
    market_id: str
    apy_bps_e6: int
    timestamp_ms: int
    source: str
    digest: bytes
    signature: bytes


class YieldOracleClient:
    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not endpoint:
            raise ValueError("oracle endpoint required")
        self._endpoint = endpoint.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_markets(self) -> list[str]:
        resp = await self._client.get(f"{self._endpoint}/v1/yield/markets")
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return list(body.get("active") or [])

    async def fetch_recent(self, market_id: str, n: int) -> list[SignedYieldSnapshot]:
        if n < 1:
            raise ValueError("n must be >= 1")
        resp = await self._client.get(
            f"{self._endpoint}/v1/yield/recent",
            params={"market_id": market_id, "n": n},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        out: list[SignedYieldSnapshot] = []
        for raw in body.get("snapshots") or []:
            out.append(
                SignedYieldSnapshot(
                    market_id=str(raw["market_id"]),
                    apy_bps_e6=int(raw["apy_bps_e6"]),
                    timestamp_ms=int(raw["timestamp_ms"]),
                    source=str(raw.get("source", "")),
                    digest=_unhex(raw["digest"]),
                    signature=_unhex(raw["signature"]),
                )
            )
        return out

    async def fetch_latest_tick(self, market_id: str, registry_id: int) -> YieldTick | None:
        """Convenience: pull the freshest signed snapshot and lift it
        into the strategy-facing `YieldTick` shape (registry id, apy,
        timestamp). Returns `None` when no snapshot has landed yet."""
        snaps = await self.fetch_recent(market_id, 1)
        if not snaps:
            return None
        head = snaps[0]
        return YieldTick(
            market_id=registry_id,
            apy_bps_e6=head.apy_bps_e6,
            timestamp_ms=head.timestamp_ms,
        )


def _unhex(s: str) -> bytes:
    s = s[2:] if s.startswith("0x") else s
    return bytes.fromhex(s)
