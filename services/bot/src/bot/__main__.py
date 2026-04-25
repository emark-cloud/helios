"""Run with: `uv run --package helios-bot python -m bot`."""

import uvicorn

from bot.service import Settings, build_app


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        build_app,
        host=settings.http_host,
        port=settings.http_port,
        factory=True,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
