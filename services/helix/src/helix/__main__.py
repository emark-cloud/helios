"""Run with: `uv run --package helios-helix python -m helix`."""

import uvicorn

from helix.service import Settings


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        "helix.service:build_app",
        host=settings.http_host,
        port=settings.http_port,
        factory=True,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
