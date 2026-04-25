"""Helios oracle service. Phase 0: health endpoint only.

Phase 1 publishes signed 1-minute price snapshots for WKITE/USDC.e/WETH.
Phase 2 adds yield-rate snapshots for the lending markets used by yield_rotation_v1.
Scenario mode replays a deterministic price series for the demo.
"""

from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="ORACLE_", env_file=".env")

    bar_interval_sec: int = 60
    signer_pk: str = Field(default="", validation_alias="ORACLE_SIGNER_PK")


def build_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]
    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, str | int]:
        return {
            "service": "oracle",
            "bar_interval_sec": settings.bar_interval_sec,
            "scenario_mode": int(settings.scenario_mode),
        }

    return create_app(name="oracle", settings=settings, routers=[router])
