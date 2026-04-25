"""Sentinel service composition. Phase 0: health endpoint only.

Phase 1 adds the six-step allocator loop from Helios.md §11.2:
1. Discover & rank strategies (via Goldsky)
2. Compute target allocation
3. Diff against current allocations
4. Drawdown check (highest priority)
5. Apply diffs
6. Fee crystallization
"""

from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env")

    name: str = "Helios Sentinel"
    fee_rate_bps: int = 500  # 5% on user net realized profit above HWM


def build_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]
    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, str | int]:
        return {
            "service": settings.name,
            "fee_rate_bps": settings.fee_rate_bps,
            "scenario_mode": int(settings.scenario_mode),
        }

    return create_app(name="sentinel", settings=settings, routers=[router])
