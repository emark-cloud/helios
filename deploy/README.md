# `deploy/` — VPS provisioning + supervision

Everything needed to bring up Helios on a fresh Ubuntu 24.04 LTS VPS. Target box for Phase 0 is a Servarica Montreal node (8 GB RAM / 2 dedicated cores / 250 GB NVMe).

## Layout

```
deploy/
├── README.md                  # this file
├── bootstrap.sh               # one-shot provisioner — run once on a fresh box
├── setup-tls.sh               # provision Let's Encrypt cert + rewrite helios.conf
├── docker-compose.prod.yml    # production stack (Postgres, Redis, prover, services)
├── ecosystem.config.cjs       # PM2 — supervises `docker compose up`, log rotation, boot-on-restart
├── env.prod.example           # production env template (NEVER commit a real .env)
├── services/
│   ├── python.Dockerfile      # generic Python service (parameterized via build args)
│   └── node.Dockerfile        # generic Node service (used by prover today)
└── nginx/
    ├── helios.conf            # reverse proxy + TLS + per-route rate limits
    └── snippets/
        └── security-headers.conf
```

## First-time provisioning

```bash
# from a fresh Ubuntu 24.04 box, as root:
ssh root@<vps-ip>
adduser helios && usermod -aG sudo helios
mkdir -p /home/helios/.ssh && cp ~/.ssh/authorized_keys /home/helios/.ssh/
chown -R helios:helios /home/helios/.ssh && chmod 700 /home/helios/.ssh

# from your workstation:
ssh-copy-id helios@<vps-ip>
scp -r deploy helios@<vps-ip>:~/
ssh helios@<vps-ip> 'sudo bash ~/deploy/bootstrap.sh'
```

`bootstrap.sh` is idempotent — re-running it just verifies state. It installs Docker + compose plugin + Node 20 + PM2 + nginx + ufw, configures swap, and creates `/srv/helios/` for app data.

## After provisioning

```bash
# on the box, as helios:
cd /srv/helios
cp ~/deploy/env.prod.example .env       # then edit with real secrets
git clone https://github.com/emark-cloud/helios.git app
cp ~/deploy/docker-compose.prod.yml app/
cp ~/deploy/ecosystem.config.cjs app/
cp -r ~/deploy/nginx /etc/nginx/helios   # adjust per nginx layout below
cd app && pm2 start ecosystem.config.cjs && pm2 save && pm2 startup
```

## How the pieces fit

- **Docker Compose** runs every service as a container with a shared bridge network. Each service uses a `services/<name>/Dockerfile` that derives from `python.Dockerfile` (or `node.Dockerfile` for the prover) by passing build args.
- **PM2** supervises a single host-level process: `docker compose up`. PM2 gives us `pm2 status`, `pm2 logs`, automatic restart on container exit, and `pm2 startup` for boot-on-VPS-restart. We're not running per-service PM2 entries because Docker already does process supervision inside each container.
- **Nginx** terminates HTTP(S), enforces per-route rate limits, and reverse-proxies to the service ports exposed on `127.0.0.1` by Docker. Public ports are 80/443 only; everything else is loopback.
- **UFW** blocks all incoming except 22/80/443.

See `bootstrap.sh` for exact versions; see `docker-compose.prod.yml` for the service graph.

## Phase status

Phase 6: production stack live. `postgres`, `redis`, `prover`, `sentinel`, `reputation`, `oracle` are all un-commented in `docker-compose.prod.yml`. `helix` and `bot` stay deferred per the post-hackathon scope cut. The generic `services/python.Dockerfile` reads `SERVICE_PACKAGE` + `SERVICE_MODULE` build args, so no per-service Dockerfile shim is needed; nginx upstreams in `nginx/helios.conf` already match the canonical service ports (8001 sentinel, 8002 reputation, 8003 oracle, 8004 prover).

## Rate limits

Per `TODO.md` Phase 6 line 475 (criterion A — scoped keys, rate limits). Values are enforced in `nginx/helios.conf` via three `limit_req_zone` declarations and a `$request_method`-keyed map. SDK clients should treat **HTTP 429** as the back-off signal (set explicitly via `limit_req_status 429`).

| Zone | Rate (per IP) | Routes | Notes |
|---|---|---|---|
| `helios_read` | 100 r/min | `GET`/`HEAD`/`OPTIONS` on `/v1/*`, `/reputation/*`, `/oracle/*` | Burst 20, nodelay. Covers the read endpoints judges + frontend hit. |
| `helios_write` | 10 r/min | `POST`/`PUT`/`PATCH`/`DELETE` on the same prefixes | Burst 2–3, nodelay. Covers `/v1/onboard` and allocator command surfaces. |
| `helios_prover` | 5 r/min | All methods on `/prove` | Burst 1, nodelay. Groth16 generation is 5–15 s per proof — sustained higher rate is always abuse. |

Method-based splitting is implemented via two `map $request_method` blocks: GET/HEAD/OPTIONS resolve the **read key** to the client's `$binary_remote_addr` (so reads count toward the read zone) and the **write key** to `""` (so reads don't count toward the write zone), and vice versa. Empty-string keys are nginx's documented mechanism for "this request is not subject to this zone."

Adjacent throttles defended elsewhere in the stack:

- **Per-strategy capital cap**: enforced in `UserVault` (`contracts/src/UserVault.sol` — `maxAllocPerStrategyBps` ACL) so a runaway allocator cannot drain a user's vault even if it bypasses Nginx entirely.
- **Strategy agent self-throttle**: `min_bar_interval` in `helios-strategy-sdk` rate-limits a strategy's own outbound trade attempts; default 60 s, tunable per class.
- **Allocator decision frequency**: enforced application-side in `services/sentinel/` (decision tick configurable via `SENTINEL_DECISION_INTERVAL`).

## Health checks + alerting

Each service exposes `GET /health` (FastAPI 200 with the service name + commit SHA). PM2's host-side process is `helios-stack` — if `docker compose up` exits, PM2 restarts it (`autorestart: true, max_restarts: 10` in `ecosystem.config.cjs`). Per-container restart is handled by Docker's own `restart: unless-stopped` policy in `docker-compose.prod.yml`.

For "alert if /health 5xx" we use a tiny cron probe rather than a full Prometheus stack — Phase 6 doesn't need a monitoring service. Drop this in `crontab -e` on the VPS:

```cron
*/5 * * * * /usr/bin/curl -fsS --max-time 5 https://${HELIOS_FQDN}/health > /dev/null || echo "health check failed at $(date -uIs)" | mail -s "[helios] health" admin@example.com
```

Replace `admin@example.com` with the on-call inbox; `mail` is provided by `mailutils` (installed by `bootstrap.sh`). PM2 logs flow to `/srv/helios/logs/stack.{out,err}.log` — rotated by Ubuntu's default `logrotate.d` config.

> **Telegram admin channel** is deferred with the rest of `services/bot/` (see TODO.md "Deferred"). Email digest is sufficient for v1.

## Postgres backups + restore

`postgres-backup.sh` runs `pg_dump` against the `postgres` compose service and writes a gzipped, mode-600 dump to `/srv/helios/backups/postgres/helios-<UTC-timestamp>.sql.gz`. The most recent 14 dumps are retained.

Cron entry (run as `helios`):

```cron
0 3 * * * /srv/helios/app/deploy/postgres-backup.sh >> /srv/helios/logs/postgres-backup.log 2>&1
```

Restore from a dump:

```bash
# Stop services that hold connections, but leave the postgres container up.
pm2 stop helios-stack
docker compose -f deploy/docker-compose.prod.yml up -d postgres

# Drop + recreate the database, then restore.
gunzip -c /srv/helios/backups/postgres/helios-<UTC-timestamp>.sql.gz \
  | docker compose -f deploy/docker-compose.prod.yml exec -T postgres \
      psql -U helios -d helios

# Resume.
pm2 start helios-stack
```

Verify the restore by hitting `https://<fqdn>/reputation/health` and `/v1/strategies` — both read from the database.

## Secrets

The repo never contains a real `.env`. Production secrets live in **two** places only:

- `/srv/helios/.env` on the VPS (mode 600, owned by `helios`). Sourced by `docker compose --env-file`.
- The corresponding service env in Vercel (frontend) — set via Vercel UI, never via `vercel env` from the repo.

Variables that must be set:

| Variable | Surface | Notes |
|---|---|---|
| `KITE_PASSPORT_SESSION_ID` | services + frontend | Passport-issued session token (MPC-backed; no raw private key). |
| `REPUTATION_SIGNER_PK` | services/reputation | Raw EOA key for signing scores into `ReputationAnchor`. |
| `ORACLE_SIGNER_PK` | services/oracle | Raw EOA key for signing price + yield commits. |
| `OPERATOR_PK` | reference-strategies | Raw EOA key the strategy operator uses for `executeWithProof` — required for WS5-prep attested-trade smoke. |
| `POSTGRES_PASSWORD` | docker-compose | Strong random; rotated on signer-key rotation events. |
| `DATABASE_URL` | services | Constructed from the above — `postgres://helios:${POSTGRES_PASSWORD}@postgres:5432/helios`. |
| `GOLDSKY_ENDPOINT` | services + frontend | Read endpoint of the deployed subgraph. Required by sentinel (allocator decisions) + reputation (score rollups). |
| `GOLDSKY_API_KEY` | subgraph deploys | Only needed when running `pnpm --filter subgraph deploy` from the workstation. |
| `PROVER_AUTH_TOKEN` | services/prover + reference strategies | Bearer token gating `POST /prove`. Empty disables auth (local dev only). VPS deploys must set a random secret. |
| `CORS_ALLOWED_ORIGINS` | services | Comma-separated list of public frontend hosts; `*` is rejected when paired with credentials. |
| `TELEGRAM_BOT_TOKEN` | services/bot | Deferred (post-hackathon). |

Sanity check from a fresh checkout:

```bash
git ls-files -z | xargs -0 grep -lE '(SIGNER_PK|API_KEY|PASSPORT_SESSION)\s*=' || echo "no committed secrets"
```

The signer-key custody story for the immutable contracts (Helios multi-sig holds owner role) is documented in `docs/threat-model.md §4`.

## VPS pre-deploy

**Pre-deploy ≥ 48 h before the judging deadline.** The judging-criteria audit (TODO.md line 479, criterion C) requires the live URL to be reachable with valid TLS during evaluation. 48 h gives:

- Let's Encrypt time to issue the cert and propagate
- DNS time to settle (`<fqdn>` → VPS IPv4 / IPv6)
- A buffer for HSTS preload pickup
- Time to verify `/health`, `/judge`, and a real attested-trade flow end-to-end

If anything fails day-of, `/judge` falls back to its self-sufficient artifacts list (RPC URL + addresses + Goldsky endpoint + Kitescan deeplinks) — judges can verify the entire system without the VPS up. Do not rely on this fallback as the primary path; it is the safety net.

## TLS

`helios.conf` is HTTPS-by-default — the HTTP server block exists only to serve the ACME challenge and 301 every other request to HTTPS. Provision a Let's Encrypt cert by pointing `<fqdn>` at the box and running:

```bash
sudo deploy/setup-tls.sh helios.example.com admin@example.com
```

The script installs `certbot` (via snap), runs the `webroot` HTTP-01 challenge, rewrites the cert paths and `server_name` in `helios.conf`, and reloads nginx. It is idempotent — re-running it with an unchanged FQDN is a no-op once the cert is provisioned, and certbot's systemd timer handles renewal automatically.

The HTTPS block enables HSTS with a 2-year `max-age` + `preload` flag. **Do not** roll the deploy back to HTTP after the first browser sees this header — the cached HSTS will refuse plaintext requests until it expires. Confirm the cert is healthy before merging the change live.
