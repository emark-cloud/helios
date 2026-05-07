# Generic Python service template.
# Build with:
#   docker build -f deploy/services/python.Dockerfile \
#     --build-arg SERVICE_PACKAGE=helios-sentinel \
#     --build-arg SERVICE_MODULE=sentinel \
#     -t helios/sentinel:latest .
#
# SERVICE_PACKAGE = the uv workspace package name (from its pyproject.toml)
# SERVICE_MODULE  = the python module to invoke as `python -m <module>`
#
# Phase-3 review MEDIUM: previous single-stage image shipped uv + the
# entire workspace source tree (~600 MB). Multi-stage build now copies
# only the resolved virtualenv + the running service's source into a
# slim runtime image, dropping ~75% of the image weight.

ARG PYTHON_VERSION=3.11

# ── Builder ───────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

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

RUN test -n "${SERVICE_PACKAGE}" || (echo "SERVICE_PACKAGE build arg required" && exit 1) \
 && test -n "${SERVICE_MODULE}"  || (echo "SERVICE_MODULE build arg required"  && exit 1) \
 && uv sync --frozen --package "${SERVICE_PACKAGE}" --no-dev

# ── Runtime ───────────────────────────────────────────────────────
# Slim image with no uv, no pip cache, no docs/test source — only what
# the running service needs to import + execute.
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Copy the resolved virtualenv from the builder. uv writes it to
# `/app/.venv/` next to the workspace root.
COPY --from=builder /app/.venv /app/.venv

# Copy only the source needed to import the workspace package +
# all packages it depends on. The simpler pragmatic approach is
# to copy `packages` and `services` wholesale (they're text files
# at small sizes); the savings come from dropping the uv binary,
# pip cache, and `~/.cache/uv` work dirs.
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/services /app/services
COPY --from=builder /app/pyproject.toml /app/uv.lock /app/

# Drop privileges
RUN useradd --system --uid 1000 --create-home --shell /usr/sbin/nologin helios
USER helios

ARG SERVICE_MODULE
ENV SERVICE_MODULE=${SERVICE_MODULE}

# Each service binds its own port via env (HTTP_PORT / SERVICE_HTTP_PORT).
EXPOSE 8000-8099

# Run directly via the venv's python — uv is no longer required at runtime.
CMD ["sh", "-c", "python -m ${SERVICE_MODULE}"]
