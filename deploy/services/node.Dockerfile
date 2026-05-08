# Generic Node service template — used by the prover today.
# Build with:
#   docker build -f deploy/services/node.Dockerfile \
#     --build-arg SERVICE_DIR=services/prover \
#     -t helios/prover:latest .

FROM node:20-bookworm-slim AS base

ENV NODE_ENV=production \
    PNPM_HOME=/usr/local/share/pnpm
ENV PATH="${PNPM_HOME}:${PATH}"

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

WORKDIR /app

ARG SERVICE_DIR
RUN test -n "${SERVICE_DIR}" || (echo "SERVICE_DIR build arg required" && exit 1)

# Copy workspace manifest first for layer caching.
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY ${SERVICE_DIR}/package.json ${SERVICE_DIR}/

RUN pnpm install --filter "./${SERVICE_DIR}..." --prod --frozen-lockfile=false

COPY ${SERVICE_DIR} ./${SERVICE_DIR}

# Make the entrypoint discoverable to the runtime CMD without baking the path.
ENV SERVICE_DIR=${SERVICE_DIR}

# `node:bookworm-slim` already ships a `node` user at UID 1000, so we
# don't claim that UID. Use the existing `node` user — it has the same
# unprivileged-runtime semantics as a custom `helios` user would.
USER node

EXPOSE 8000-8099
CMD ["sh", "-c", "node ${SERVICE_DIR}/src/index.js"]
