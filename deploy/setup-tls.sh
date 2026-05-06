#!/usr/bin/env bash
# Provision a Let's Encrypt cert for the Helios VPS and rewrite
# `helios.conf` to use it.
#
# Usage (run as root or with sudo on the VPS):
#   sudo deploy/setup-tls.sh helios.example.com [admin@example.com]
#
# Idempotent — safe to re-run. Re-runs renew the cert if necessary and
# leave nginx config untouched.

set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "must run as root (use sudo)" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <fqdn> [admin-email]" >&2
  exit 2
fi

FQDN="$1"
EMAIL="${2:-admin@$FQDN}"

NGINX_AVAILABLE="/etc/nginx/sites-available/helios.conf"
ACME_WEBROOT="/var/www/certbot"

if [[ ! -f "$NGINX_AVAILABLE" ]]; then
  echo "expected $NGINX_AVAILABLE — run after copying deploy/nginx/helios.conf" >&2
  exit 3
fi

# 1. Install certbot if needed (Ubuntu 24.04 ships with snap).
if ! command -v certbot >/dev/null 2>&1; then
  echo "[setup-tls] installing certbot via snap"
  apt-get update -y
  apt-get install -y snapd
  snap install --classic certbot
  ln -sf /snap/bin/certbot /usr/bin/certbot
fi

# 2. ACME webroot for the HTTP-01 challenge. The HTTP server block in
# helios.conf already serves `/.well-known/acme-challenge/` from here.
mkdir -p "$ACME_WEBROOT"
chown -R www-data:www-data "$ACME_WEBROOT"

# 3. Obtain or renew the cert. `--keep-until-expiring` means a fresh
# run before the cert is near expiry is a no-op.
echo "[setup-tls] requesting cert for $FQDN (email: $EMAIL)"
certbot certonly \
  --non-interactive \
  --agree-tos \
  --webroot --webroot-path "$ACME_WEBROOT" \
  --email "$EMAIL" \
  --keep-until-expiring \
  --domains "$FQDN"

# 4. Rewrite helios.conf placeholders. Idempotent — sed is a no-op once
# the FQDN is in place. We replace BOTH the cert paths and the
# `server_name _;` line on the HTTPS block (HTTP block stays `_` so it
# catches every name and redirects).
echo "[setup-tls] rewriting helios.conf"
sed -i "s|/etc/letsencrypt/live/HELIOS_FQDN/|/etc/letsencrypt/live/$FQDN/|g" "$NGINX_AVAILABLE"
# Only rewrite the second `server_name _;` (the HTTPS block). awk-pass
# tracks which `server {` block we're in.
awk -v fqdn="$FQDN" '
  /^server *{/ { blocks++ }
  blocks == 2 && /^    server_name +_;/ { print "    server_name " fqdn ";"; next }
  { print }
' "$NGINX_AVAILABLE" > "$NGINX_AVAILABLE.tmp" && mv "$NGINX_AVAILABLE.tmp" "$NGINX_AVAILABLE"

# 5. Reload nginx.
echo "[setup-tls] testing nginx config"
nginx -t
systemctl reload nginx

# 6. Auto-renewal. snap installs a systemd timer; verify it's enabled.
systemctl enable --now snap.certbot.renew.timer 2>/dev/null || true

echo "[setup-tls] done — https://$FQDN/health should return 200"
