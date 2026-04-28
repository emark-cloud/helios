"""Run with: `uv run --package helios-sentinel python -m sentinel`."""

import uvicorn

from sentinel.service import Settings


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        "sentinel.service:build_app",
        host=settings.http_host,
        port=settings.http_port,
        factory=True,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
