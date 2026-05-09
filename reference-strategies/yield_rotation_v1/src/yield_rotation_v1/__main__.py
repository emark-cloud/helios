"""Run with: `uv run --package helios-reference-yield-rotation-v1 python -m yield_rotation_v1`.

The FastAPI runner depends on the workspace-only `helios-service-template`
package. PyPI installs that omit the `[service]` extra get a clear
ImportError instead of a confusing Pyright/runtime traceback.
"""

import uvicorn

try:
    from yield_rotation_v1.service import Settings, build_app
except ImportError as exc:  # pragma: no cover - install-time path
    raise SystemExit(
        "yield_rotation_v1.__main__ requires the FastAPI service template "
        "(`helios-service-template`), which only ships with the in-repo "
        "workspace. Install with `pip install "
        "helios-reference-yield-rotation-v1[service]` from a workspace "
        "checkout, or import `yield_rotation_v1.runtime` directly to run "
        "the strategy as a library."
    ) from exc


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        "yield_rotation_v1.service:build_app",
        host=settings.http_host,
        port=settings.http_port,
        factory=True,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
