#!/usr/bin/env bash
# backup.sh — Backup the SQLite database
# Usage: ./scripts/backup.sh [destination_dir]
# Cron example: 0 2 * * * /opt/unifi-toolkit/scripts/backup.sh /var/backups/toolkit

set -euo pipefail
cd "$(dirname "$0")/.."

DEST="${1:-./backups}"
mkdir -p "$DEST"

TS=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${DEST}/toolkit-db-${TS}.db"

# SQLite online backup via docker exec
docker compose exec -T app sqlite3 /app/data/toolkit.db ".backup '/app/data/backup-${TS}.db'"
docker compose cp "app:/app/data/backup-${TS}.db" "$BACKUP_FILE"
docker compose exec -T app rm -f "/app/data/backup-${TS}.db"

# Compress
gzip "$BACKUP_FILE"
echo "✓  Backup saved: ${BACKUP_FILE}.gz ($(du -h "${BACKUP_FILE}.gz" | cut -f1))"

# Keep last 30 backups
find "$DEST" -name "toolkit-db-*.db.gz" -mtime +30 -delete
echo "✓  Old backups cleaned (kept last 30 days)"
