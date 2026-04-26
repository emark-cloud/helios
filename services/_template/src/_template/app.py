"""FastAPI app factory shared across services.

Each service calls `create_app(...)` with its name, settings, and routers.
The factory wires up structured logging, CORS for the frontend, a /health
endpoint, and lifespan management for the database engine.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from _template.config import BaseServiceSettings
from _template.db import get_engine
from _template.logging import configure_logging, get_logger


def create_app(
    *,
    name: str,
    settings: BaseServiceSettings,
    routers: list[APIRouter] | None = None,
    on_startup: list[Callable[[], Awaitable[None]]] | None = None,
    on_shutdown: list[Callable[[], Awaitable[None]]] | None = None,
) -> FastAPI:
    """Build a FastAPI app with the Helios conventions baked in."""
    configure_logging(level=settings.log_level, json_output=settings.environment != "development")
    log = get_logger(name)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log.info("service.starting", name=name, env=settings.environment)
        if settings.database_url:
            get_engine(settings.database_url)
        for hook in on_startup or []:
            await hook()
        try:
            yield
        finally:
            for hook in on_shutdown or []:
                await hook()
            log.info("service.stopping", name=name)

    app = FastAPI(title=f"Helios :: {name}", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in deploy config
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": name}

    for router in routers or []:
        app.include_router(router)

    return app
