# Generic Python service template.
# Build with:
#   docker build -f deploy/services/python.Dockerfile \
#     --build-arg SERVICE_PACKAGE=helios-sentinel \
#     --build-arg SERVICE_MODULE=sentinel \
#     -t helios/sentinel:latest .
#
# SERVICE_PACKAGE = the uv workspace package name (from its pyproject.toml)
# SERVICE_MODULE  = the python module to invoke as `python -m <module>`

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# uv for fast workspace-aware installs
RUN pip install --no-cache-dir "uv>=0.5"

WORKDIR /app

# Copy workspace metadata first — gives us deterministic dep layer caching.
# When pyproject/lockfile don't change, deps don't reinstall.
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services

ARG SERVICE_PACKAGE
ARG SERVICE_MODULE
ENV SERVICE_MODULE=${SERVICE_MODULE}

RUN test -n "${SERVICE_PACKAGE}" || (echo "SERVICE_PACKAGE build arg required" && exit 1) \
 && test -n "${SERVICE_MODULE}"  || (echo "SERVICE_MODULE build arg required"  && exit 1) \
 && uv sync --frozen --package "${SERVICE_PACKAGE}" --no-dev

# Drop privileges
RUN useradd --system --uid 1000 --create-home --shell /usr/sbin/nologin helios
USER helios

# Each service binds its own port via env (HTTP_PORT / SERVICE_HTTP_PORT).
EXPOSE 8000-8099

# `uv run` resolves the right virtualenv for the workspace package.
CMD ["sh", "-c", "uv run --package ${SERVICE_MODULE_PKG:-helios-${SERVICE_MODULE}} python -m ${SERVICE_MODULE}"]
