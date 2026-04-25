FROM node:20-bookworm-slim

WORKDIR /app

COPY package.json pnpm-lock.yaml* ./
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate \
 && pnpm install --prod --frozen-lockfile=false

COPY src ./src

ENV NODE_ENV=production
EXPOSE 8004
CMD ["node", "src/index.js"]
