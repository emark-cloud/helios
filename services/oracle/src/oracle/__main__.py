"""Run with: `uv run --package helios-oracle python -m oracle`."""

import uvicorn

from oracle.service import Settings


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    # Pass the factory as an import string so uvicorn's reload mode can
    # re-import on change. Passing the callable directly is incompatible
    # with `reload=True`.
    uvicorn.run(
        "oracle.service:build_app",
        host=settings.http_host,
        port=settings.http_port,
        factory=True,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
