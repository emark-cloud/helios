"""HTTP client for `services/prover`.

Single endpoint: `POST /prove { strategyClass, witnessInputs }` →
`{ proof, publicSignals }`. The prover times out internally at 30s
and responds 503 on snarkjs faults; we surface those as
`ProverDegraded` so the runtime can log + skip the bar without
falling back to anything (the spec requires no silent fallback —
`Helios.md §7.6`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class ProofResult:
    """The prover's response. `proof` is the snarkjs JSON shape;
    `public_signals` is the array of decimal-string field elements.
    """

    proof: dict[str, Any]
    public_signals: list[str]


class ProverDegraded(RuntimeError):
    """Prover returned 503 (snarkjs fault or wall-time exceeded)."""


class ProverClient:
    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient | None = None,
        timeout_sec: float = 35.0,
        auth_token: str = "",
    ) -> None:
        if not endpoint:
            raise ValueError("prover endpoint required")
        self._endpoint = endpoint.rstrip("/")
        # 35s > prover's internal 30s ceiling so we always see the 503,
        # never an httpx timeout, when the prover is the slow path.
        self._client = client or httpx.AsyncClient(timeout=timeout_sec)
        self._owns_client = client is None
        # Optional bearer token (HIGH #17 in `docs/phase-3-review.md`).
        self._auth_token = auth_token

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def prove(
        self,
        *,
        strategy_class: str,
        witness_inputs: dict[str, Any],
    ) -> ProofResult:
        headers = {"Authorization": f"Bearer {self._auth_token}"} if self._auth_token else None
        resp = await self._client.post(
            f"{self._endpoint}/prove",
            json={"strategyClass": strategy_class, "witnessInputs": witness_inputs},
            headers=headers,
        )
        if resp.status_code == 429:
            raise ProverDegraded(resp.json().get("error", "prover busy"))
        if resp.status_code == 503:
            raise ProverDegraded(resp.json().get("error", "prover degraded"))
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return ProofResult(
            proof=body["proof"],
            public_signals=[str(s) for s in body.get("publicSignals") or []],
        )
