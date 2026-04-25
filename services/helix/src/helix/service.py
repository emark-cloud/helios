"""Helios Helix service. Phase 0: health endpoint only.

Phase 3 implements the regime-adaptive fee factor + correlation-aware
greedy pick on top of the AllocatorSDK. Built from scratch on the SDK
to validate that third-party allocator development is real.
"""

from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="HELIX_", env_file=".env")

    name: str = "Helios Helix"
    fee_rate_bps: int = 600  # 6% — slightly higher than Sentinel's 5%
    max_pairwise_correlation: float = 0.7


def build_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]
    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, str | int | float]:
        return {
            "service": settings.name,
            "fee_rate_bps": settings.fee_rate_bps,
            "max_pairwise_correlation": settings.max_pairwise_correlation,
        }

    return create_app(name="helix", settings=settings, routers=[router])
