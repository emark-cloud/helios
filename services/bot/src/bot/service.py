"""Telegram bot service. Phase 0: health endpoint only.

Phase 4 wires this to the Sentinel/Helix WebSocket event streams and
fires text-forward pings: StrategyAllocated, StrategyDefunded,
RebalanceComplete, FeeAccrued, WithdrawalReady.
"""

from _template import BaseServiceSettings, create_app
from fastapi import APIRouter, FastAPI
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="BOT_", env_file=".env")

    bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")


def build_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]
    router = APIRouter(prefix="/v1")

    @router.get("/")
    async def root() -> dict[str, str | bool]:
        return {
            "service": "bot",
            "configured": bool(settings.bot_token),
        }

    return create_app(name="bot", settings=settings, routers=[router])
