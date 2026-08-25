#!/usr/bin/env bash
set -euo pipefail
BACKEND_DIR=/srv/zipterior/backups/backend
DB_DIR=/srv/zipterior/backups/database
latest_backend=$(find "$BACKEND_DIR" -maxdepth 1 -type f -name '*.tar.gz' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2- || true)
latest_db=$(find "$DB_DIR" -maxdepth 1 -type f -name '*.dump' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2- || true)
[[ -n "$latest_backend" && -f "$latest_backend" ]] || { echo BACKEND_BACKUP_MISSING; exit 1; }
[[ -n "$latest_db" && -f "$latest_db" ]] || { echo DATABASE_BACKUP_MISSING; exit 1; }
tar -tzf "$latest_backend" >/dev/null
pg_restore -l "$latest_db" >/dev/null
echo "LATEST_BACKEND_BACKUP=$latest_backend"
echo "LATEST_DATABASE_BACKUP=$latest_db"
echo BACKUP_ARCHIVE_VERIFY_OK
