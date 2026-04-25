#!/usr/bin/env bash
# Helios VPS bootstrap — Ubuntu 24.04 LTS.
# Idempotent. Re-runs verify state without breaking things.
# Run as root or via sudo: `sudo bash deploy/bootstrap.sh`

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "must run as root (try: sudo bash $0)" >&2
  exit 1
fi

UBUNTU_VERSION="$(lsb_release -rs 2>/dev/null || true)"
if [[ "${UBUNTU_VERSION}" != "24.04" ]]; then
  echo "warning: tested on Ubuntu 24.04, found ${UBUNTU_VERSION:-unknown}; continuing"
fi

log() { echo "==> $*"; }

# ── 1. Base packages ────────────────────────────────────────
log "apt update + base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl gnupg lsb-release \
  ufw nginx git build-essential \
  htop ncdu jq unzip vim

# ── 2. Docker + compose plugin ──────────────────────────────
if ! command -v docker >/dev/null; then
  log "installing Docker"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  log "Docker present: $(docker --version)"
fi

# ── 3. Node 20 + PM2 ────────────────────────────────────────
if ! command -v node >/dev/null || [[ "$(node -v | cut -d. -f1)" != "v20" ]]; then
  log "installing Node 20"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -qq nodejs
fi
log "Node: $(node -v) / npm: $(npm -v)"

if ! command -v pm2 >/dev/null; then
  log "installing PM2"
  npm install -g pm2@5
else
  log "PM2 present: $(pm2 -v)"
fi

# ── 4. helios user (if not present) ─────────────────────────
if ! id -u helios >/dev/null 2>&1; then
  log "creating helios user"
  adduser --disabled-password --gecos "" helios
  usermod -aG docker,sudo helios
  echo "helios ALL=(ALL) NOPASSWD: /bin/systemctl restart nginx, /bin/systemctl reload nginx" \
    > /etc/sudoers.d/helios-nginx
  chmod 440 /etc/sudoers.d/helios-nginx
else
  usermod -aG docker helios
  log "helios user present"
fi

# ── 5. App directories ──────────────────────────────────────
log "preparing /srv/helios"
mkdir -p /srv/helios/{app,data/postgres,data/redis,logs,backups}
chown -R helios:helios /srv/helios

# ── 6. Swap (8 GB RAM box benefits from a 2 GB safety net) ──
if ! swapon --show | grep -q '/swapfile'; then
  log "creating 2 GB swapfile"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
  sysctl vm.swappiness=10
  echo "vm.swappiness=10" > /etc/sysctl.d/99-helios.conf
else
  log "swap already active: $(swapon --show --noheadings | head -1)"
fi

# ── 7. UFW (deny incoming, allow ssh + http/s) ──────────────
log "configuring UFW"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow http
ufw allow https
ufw --force enable

# ── 8. Nginx baseline ───────────────────────────────────────
log "enabling nginx"
systemctl enable --now nginx
# Real config is dropped in by the post-bootstrap step (see deploy/nginx/).

# ── 9. Logrotate for Docker container logs ──────────────────
cat >/etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
JSON
systemctl restart docker

log "bootstrap complete"
log "next: copy deploy/{docker-compose.prod.yml,ecosystem.config.cjs,nginx/} into place,"
log "      git clone the repo into /srv/helios/app, fill /srv/helios/.env, and pm2 start."
