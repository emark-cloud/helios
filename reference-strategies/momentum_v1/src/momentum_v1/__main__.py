"""Run with: `uv run --package helios-reference-momentum-v1 python -m momentum_v1`.

The FastAPI runner depends on the workspace-only `helios-service-template`
package. PyPI installs that omit the `[service]` extra get a clear
ImportError instead of a confusing Pyright/runtime traceback.
"""

import uvicorn

try:
    from momentum_v1.service import Settings, build_app
except ImportError as exc:  # pragma: no cover - install-time path
    raise SystemExit(
        "momentum_v1.__main__ requires the FastAPI service template "
        "(`helios-service-template`), which only ships with the in-repo "
        "workspace. Install with `pip install helios-reference-momentum-v1"
        "[service]` from a workspace checkout, or import "
        "`momentum_v1.runtime` directly to run the strategy as a library."
    ) from exc


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    # Pass the factory as an import string so uvicorn's reload mode can
    # re-import on change. Passing the callable directly is incompatible
    # with `reload=True` and silently exits after a warning.
    uvicorn.run(
        "momentum_v1.service:build_app",
        host=settings.http_host,
        port=settings.http_port,
        factory=True,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
