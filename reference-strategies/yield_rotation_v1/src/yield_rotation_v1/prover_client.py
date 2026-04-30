"""HTTP client for `services/prover`.

Same protocol as the momentum/MR clients — `POST /prove
{ strategyClass, witnessInputs }` → `{ proof, publicSignals }`.
Failures surface as `ProverDegraded` so the runtime can log + skip the
tick without falling back to anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class ProofResult:
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
    ) -> None:
        if not endpoint:
            raise ValueError("prover endpoint required")
        self._endpoint = endpoint.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_sec)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def prove(
        self,
        *,
        strategy_class: str,
        witness_inputs: dict[str, Any],
    ) -> ProofResult:
        resp = await self._client.post(
            f"{self._endpoint}/prove",
            json={"strategyClass": strategy_class, "witnessInputs": witness_inputs},
        )
        if resp.status_code == 503:
            raise ProverDegraded(resp.json().get("error", "prover degraded"))
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return ProofResult(
            proof=body["proof"],
            public_signals=[str(s) for s in body.get("publicSignals") or []],
        )
