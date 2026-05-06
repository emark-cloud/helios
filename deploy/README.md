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

This is **Phase 0 scaffolding** — the templates are in place and parameterized. Phase 1 fills in:

- per-service Dockerfile shims under `services/<name>/Dockerfile` extending `python.Dockerfile` with the right `SERVICE_PACKAGE` and entrypoint
- compose entries un-commented as each service has real behavior
- nginx upstream config validated against the actual ports

## TLS

`helios.conf` is HTTPS-by-default — the HTTP server block exists only to serve the ACME challenge and 301 every other request to HTTPS. Provision a Let's Encrypt cert by pointing `<fqdn>` at the box and running:

```bash
sudo deploy/setup-tls.sh helios.example.com admin@example.com
```

The script installs `certbot` (via snap), runs the `webroot` HTTP-01 challenge, rewrites the cert paths and `server_name` in `helios.conf`, and reloads nginx. It is idempotent — re-running it with an unchanged FQDN is a no-op once the cert is provisioned, and certbot's systemd timer handles renewal automatically.

The HTTPS block enables HSTS with a 2-year `max-age` + `preload` flag. **Do not** roll the deploy back to HTTP after the first browser sees this header — the cached HSTS will refuse plaintext requests until it expires. Confirm the cert is healthy before merging the change live.
