"""Reputation Engine service composition. Phase 0: health endpoint only.

Phase 1 implements a P&L + proof-validity score; Phase 2 ships the full
multi-factor formula from Helios.md §8.2.
"""

from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="REPUTATION_", env_file=".env")

    poll_interval_sec: int = 60
    recompute_cadence_sec: int = 300
    signer_pk: str = Field(default="", validation_alias="REPUTATION_SIGNER_PK")


def build_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]
    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, str | int]:
        return {
            "service": "reputation",
            "poll_interval_sec": settings.poll_interval_sec,
            "scenario_mode": int(settings.scenario_mode),
        }

    return create_app(name="reputation", settings=settings, routers=[router])
