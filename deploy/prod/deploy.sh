#!/usr/bin/env bash
# Run as root on the production host, from the verified upload directory.
set -Eeuo pipefail
umask 027

release_id=${1:?Expected run-number-attempt-commit}
[[ "$release_id" =~ ^[0-9]+-[0-9]+-[0-9a-f]{40}$ ]] || exit 2
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 2; }
base=/opt/aicase-prod
state=/var/lib/aicase-prod
env_file=/etc/aicase-prod/backend.env
service=aicase-prod
unit_dir=/etc/systemd/system
domain=popomo.chunpat.cc
release="$base/releases/$release_id"
archive="$PWD/release.tar.gz"
test -f "$archive"
test -f "$env_file"
# Refuse to publish before bootstrap has provisioned HTTPS.
test -s /etc/letsencrypt/live/popomo.chunpat.cc/fullchain.pem
test -s /etc/letsencrypt/live/popomo.chunpat.cc/privkey.pem
id aicase-prod >/dev/null
command -v pg_dump >/dev/null
command -v flock >/dev/null
exec 9>/var/lock/aicase-prod-deploy.lock
flock -n 9 || { echo 'Another production deployment is running.' >&2; exit 1; }

mkdir -p "$base/releases" "$state/backups"
test ! -e "$release"
mkdir "$release"
tar --extract --gzip --file "$archive" --directory "$release" --no-same-owner
[[ $(cat "$release/VERSION") == "${release_id##*-}" ]]
python3 -m venv "$release/.venv"
"$release/.venv/bin/python" -m pip install --disable-pip-version-check -r "$release/backend/requirements.txt"
chown -R aicase-prod:aicase-prod "$release"
chmod o+x "$release" "$release/frontend" "$release/backend"
chmod -R o+rX "$release/frontend/storefront"

set -a
# This root-owned file uses shell-compatible KEY=value assignments.
# shellcheck source=/dev/null
source "$env_file"
set +a
: "${DJANGO_SECRET_KEY:?}" "${AI_CONFIG_ENCRYPTION_KEY:?}" "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"
[[ ${DJANGO_DEBUG:-1} == 0 && ${DJANGO_TRUST_PROXY:-0} == 1 ]]
[[ ${DJANGO_MEDIA_ROOT:-} == "$state/media" ]]
export PGHOST=${POSTGRES_HOST:-127.0.0.1} PGPORT=${POSTGRES_PORT:-5432}
export PGUSER=$POSTGRES_USER PGPASSWORD=$POSTGRES_PASSWORD PGDATABASE=$POSTGRES_DB
manage() { runuser -u aicase-prod -- "$release/.venv/bin/python" "$release/backend/manage.py" "$@"; }
manage check
nginx -t

previous=''
if [[ -L "$base/current" ]]; then previous=$(readlink -f "$base/current"); fi
switched=0
stopped=0
healthy() {
    curl --fail --silent --show-error --max-time 5 \
        -H "Host: $domain" -H 'X-Forwarded-Proto: https' \
        "http://127.0.0.1:18012$1" >/dev/null
}
wait_healthy() {
    for ((attempt=0; attempt<30; attempt++)); do
        if healthy /api/health/ && healthy /api/v1/catalog/; then return 0; fi
        sleep 2
    done
    return 1
}
cleanup() {
    status=$?
    trap - EXIT
    if (( status != 0 && stopped )); then
        echo 'Deployment failed; restoring the previous application release.' >&2
        if [[ -n "$previous" && -d "$previous" ]]; then
            ln -sfn "$previous" "$base/current.rollback"
            mv -Tf "$base/current.rollback" "$base/current"
            if systemctl restart "$service" && wait_healthy; then
                rm -f "$state/deploying"
            else
                echo 'Rollback needs attention; maintenance mode remains enabled.' >&2
            fi
        else
            systemctl stop "$service" || true
            if (( switched )); then rm -f "$base/current"; fi
            echo 'First deployment failed; maintenance mode remains enabled.' >&2
        fi
        echo 'Database migrations were NOT reversed. Use a compatible fix or the saved backup.' >&2
    elif (( status != 0 )); then
        rm -f "$state/deploying"
    fi
    exit "$status"
}
trap cleanup EXIT

# Nginx serves 503 while draining, backing up and switching releases.
touch "$state/deploying"
# A stopped writer may have sent a request: its durable state is never replayed.
if [[ -f "$unit_dir/aicase-prod-supplier-orders.service" ]]; then
    systemctl stop aicase-prod-supplier-orders.service
fi
if [[ -f "$unit_dir/aicase-prod-inventory.service" ]]; then
    systemctl stop aicase-prod-inventory.service
fi
if [[ -n "$previous" && -f "$previous/backend/manage.py" ]]; then
    drained=0
    for ((attempt=0; attempt<60; attempt++)); do
        active=$(runuser -u aicase-prod -- "$previous/.venv/bin/python" "$previous/backend/manage.py" shell -c \
            "from management_api.models import AIRender; print(AIRender.objects.filter(status__in=['queued','generating']).count())" | tail -n 1)
        if [[ "$active" == 0 ]]; then drained=1; break; fi
        sleep 5
    done
    (( drained )) || { echo 'AI jobs are still active; retry deployment after they finish.' >&2; exit 1; }
fi
stopped=1
systemctl stop "$service"
backup="$state/backups/$release_id"
mkdir -m 700 "$backup"
pg_dump --format=custom --file="$backup/database.dump"
pg_restore --list "$backup/database.dump" >/dev/null
cp "$env_file" "$backup/backend.env"
tar -czf "$backup/media.tar.gz" -C "$state" media
printf '%s\n' "$previous" > "$backup/previous-release"
touch "$backup/COMPLETE"

manage migrate --noinput
# Seed only the first release; future deployments preserve managed catalog data.
if [[ -z "$previous" ]]; then
    manage seed_catalog
    manage seed_ai_recipes
    manage seed_ai_style_pack
    manage seed_phone_templates --only-supplied
fi
manage collectstatic --noinput
chmod -R o+rX "$release/backend/staticfiles"
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
switched=1
systemctl start "$service"
wait_healthy || { echo 'New release failed health checks.' >&2; exit 1; }
install -m 644 "$release/deploy/prod/aicase-prod-supplier-orders.service" "$unit_dir/"
install -m 644 "$release/deploy/prod/aicase-prod-supplier-orders.timer" "$unit_dir/"
install -m 644 "$release/deploy/prod/aicase-prod-ai-cleanup.service" "$unit_dir/"
install -m 644 "$release/deploy/prod/aicase-prod-ai-cleanup.timer" "$unit_dir/"
install -m 644 "$release/deploy/prod/aicase-prod-inventory.service" "$unit_dir/"
install -m 644 "$release/deploy/prod/aicase-prod-inventory.timer" "$unit_dir/"
systemctl daemon-reload
systemctl enable --now aicase-prod-ai-cleanup.timer
systemctl enable --now aicase-prod-supplier-orders.timer
# Install the daily backup after a healthy release.
install -m 700 "$release/deploy/prod/backup.sh" /usr/local/sbin/aicase-prod-backup
install -m 644 "$release/deploy/prod/aicase-prod-backup.service" "$unit_dir/"
install -m 644 "$release/deploy/prod/aicase-prod-backup.timer" "$unit_dir/"
systemctl daemon-reload
systemctl enable --now aicase-prod-backup.timer
rm -f "$state/deploying"
systemctl enable --now aicase-prod-inventory.timer
printf 'Deployed %s to https://%s\n' "$release_id" "$domain"
