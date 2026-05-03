# External-contributor smoke image — proves a third party can install
# the Helios SDK + CLI and run `helios backtest` / `helios simulate`
# without touching the rest of the repo.
#
# Three install modes:
#   local    (PR5.A default) — COPY the four workspace packages in
#            dependency order and pip-install each one. No external
#            dependency; runs from the repo's working tree.
#   release  (PR5.B canonical) — fetch the four wheels from a GitHub
#            Release (or any URL serving them) and pip-install via
#            --find-links so transitive deps still resolve from PyPI.
#            Requires WHEEL_BASE_URL.
#   testpypi (future) — pip-install from test-PyPI once
#            helios-trader-cli / helios-allocator-sdk / helios-contracts-abi
#            have their trusted-publisher entries registered.

FROM python:3.12-slim

ARG INSTALL_MODE=local
ARG SDK_VERSION=0.1.0
# Base URL where the four wheels live for INSTALL_MODE=release. For a
# GitHub Release this is
# `https://github.com/<owner>/<repo>/releases/download/sdk-v<version>/`.
# Defaults are intentionally empty so a misconfigured release build
# fails loudly rather than silently fetching the wrong artifacts.
ARG WHEEL_BASE_URL=""

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/helios

# release mode runs first so it's a fully self-contained layer when
# selected — no workspace COPY needed, just curl + pip.
RUN if [ "$INSTALL_MODE" = "release" ]; then \
        if [ -z "$WHEEL_BASE_URL" ]; then \
            echo "INSTALL_MODE=release requires --build-arg WHEEL_BASE_URL=<url>" >&2 ; \
            exit 1 ; \
        fi && \
        apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
        rm -rf /var/lib/apt/lists/* && \
        mkdir -p /tmp/helios-wheels && \
        BASE="${WHEEL_BASE_URL%/}" && \
        for pkg in helios_contracts_abi helios_strategy_sdk helios_allocator_sdk helios_trader_cli; do \
            wheel="${pkg}-${SDK_VERSION}-py3-none-any.whl" && \
            echo "Fetching ${wheel} from ${BASE}/" && \
            curl -fsSL --retry 5 --retry-delay 2 -o "/tmp/helios-wheels/${wheel}" "${BASE}/${wheel}" ; \
        done && \
        pip install \
            --find-links /tmp/helios-wheels \
            --extra-index-url https://pypi.org/simple/ \
            helios-trader-cli && \
        rm -rf /tmp/helios-wheels ; \
    fi

# testpypi install: pip-install helios-strategy-sdk + helios-trader-cli
# with the public PyPI fallback for transitive deps (test-PyPI doesn't
# mirror numpy / pydantic / web3 / …).
RUN if [ "$INSTALL_MODE" = "testpypi" ]; then \
        pip install \
            --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            "helios-strategy-sdk==${SDK_VERSION}" \
            "helios-trader-cli==${SDK_VERSION}" ; \
    fi

# local install pulls the four packages from the workspace COPY. The
# COPY happens unconditionally so the layer cache is shared with
# release/testpypi rebuilds — pip just doesn't run on the temp dir
# unless INSTALL_MODE=local.
COPY packages/contracts-abi-py /tmp/helios-pkgs/contracts-abi-py
COPY packages/strategy-sdk /tmp/helios-pkgs/strategy-sdk
COPY packages/allocator-sdk /tmp/helios-pkgs/allocator-sdk
COPY packages/helios-cli /tmp/helios-pkgs/helios-cli

RUN if [ "$INSTALL_MODE" = "local" ]; then \
        pip install \
            /tmp/helios-pkgs/contracts-abi-py \
            /tmp/helios-pkgs/strategy-sdk \
            /tmp/helios-pkgs/allocator-sdk \
            /tmp/helios-pkgs/helios-cli ; \
    fi && rm -rf /tmp/helios-pkgs

COPY docs/external-contributor/examples /opt/helios/examples

# Smoke runs as a non-root user — proves the install doesn't depend
# on root-owned site-packages.
RUN useradd --create-home --uid 1001 contributor \
    && chown -R contributor:contributor /opt/helios
USER contributor

ENTRYPOINT ["helios"]
CMD ["--help"]
