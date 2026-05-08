#!/usr/bin/env bash
# Helios Postgres backup — pg_dump of the `helios` database to a
# timestamped, gzipped, mode-0600 dump under /srv/helios/backups/postgres.
# Retains the most recent 14 dumps; older ones are pruned.
#
# Run as the `helios` user. Cron entry (in `crontab -e`):
#   0 3 * * * /srv/helios/app/deploy/postgres-backup.sh >> /srv/helios/logs/postgres-backup.log 2>&1
#
# Restore: see deploy/README.md "Postgres backups + restore" section.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/helios/backups/postgres}"
RETAIN="${RETAIN:-14}"
COMPOSE_FILE="${COMPOSE_FILE:-/srv/helios/app/deploy/docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-/srv/helios/.env}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$BACKUP_DIR/helios-$stamp.sql.gz"
tmp="$out.partial"

echo "[$(date -uIs)] starting backup → $out"

# Run pg_dump inside the running postgres container so we don't need a
# host-side psql client and we pick up the right credentials from the
# container's env. -Z 0 disables pg_dump's own gzip; we pipe through gzip
# so we can use -1 (fast) consistently across hosts.
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump --clean --if-exists --no-owner --no-privileges -U helios -d helios \
  | gzip -1 > "$tmp"

mv "$tmp" "$out"
chmod 600 "$out"

# Prune old dumps. -t sorts by mtime; tail skips the newest $RETAIN.
find "$BACKUP_DIR" -maxdepth 1 -name 'helios-*.sql.gz' -type f -printf '%T@ %p\n' \
  | sort -nr \
  | awk -v keep="$RETAIN" 'NR > keep { print $2 }' \
  | while read -r old; do
      echo "[$(date -uIs)] pruning $old"
      rm -f "$old"
    done

echo "[$(date -uIs)] backup complete: $(du -h "$out" | cut -f1)"
