#!/usr/bin/env bash
# Local daily backup, executed as root by systemd (or BaoTa Shell task).
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || exit 2
state=/var/lib/aicase-prod
exec 9>/var/lock/aicase-prod-deploy.lock
flock -w 1800 9
# shellcheck source=/dev/null
source /etc/aicase-prod/backend.env
export PGHOST=${POSTGRES_HOST:-127.0.0.1} PGPORT=${POSTGRES_PORT:-5432}
export PGUSER=$POSTGRES_USER PGPASSWORD=$POSTGRES_PASSWORD PGDATABASE=$POSTGRES_DB
backup="$state/daily-backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$backup.partial"
trap 'rm -rf -- "$backup.partial"' EXIT
pg_dump --format=custom --file="$backup.partial/database.dump"
pg_restore --list "$backup.partial/database.dump" >/dev/null
cp /etc/aicase-prod/backend.env "$backup.partial/backend.env"
tar -czf "$backup.partial/media.tar.gz" -C "$state" media
readlink -f /opt/aicase-prod/current > "$backup.partial/previous-release"
touch "$backup.partial/COMPLETE"
mv "$backup.partial" "$backup"
trap - EXIT
# Remove only complete daily snapshots older than 14 days after a new success.
find "$state/daily-backups" -mindepth 2 -maxdepth 2 -type f -name COMPLETE -mtime +14 -print0 |
    while IFS= read -r -d '' marker; do rm -rf -- "${marker%/COMPLETE}"; done
printf 'Backup complete: %s\n' "$backup"
