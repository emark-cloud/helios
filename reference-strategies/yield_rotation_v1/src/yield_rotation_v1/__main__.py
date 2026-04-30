"""Run with: `uv run --package helios-reference-yield-rotation-v1 python -m yield_rotation_v1`."""

import uvicorn

from yield_rotation_v1.service import Settings, build_app


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
