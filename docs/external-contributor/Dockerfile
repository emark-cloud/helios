# External-contributor smoke image — proves a third party can install
# the Helios SDK + CLI and run `helios backtest` / `helios simulate`
# without touching the rest of the repo.
#
# Build context is the repo root. PR5.A installs from local workspace
# source so the smoke can run without any test-PyPI publish; PR5.B
# flips INSTALL_MODE=testpypi once the OIDC trusted publisher is wired.

FROM python:3.12-slim

ARG INSTALL_MODE=local
ARG SDK_VERSION=0.1.0

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/helios

# Local install: COPY the four workspace packages in dependency order
# and pip-install each one.
#
# test-PyPI install: pip-install helios-strategy-sdk + helios-cli with
# the public PyPI fallback for transitive deps (test-PyPI doesn't
# mirror numpy / pydantic / web3 / …).
RUN if [ "$INSTALL_MODE" = "testpypi" ]; then \
        pip install \
            --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            "helios-strategy-sdk==${SDK_VERSION}" \
            "helios-cli==${SDK_VERSION}" ; \
    fi

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
