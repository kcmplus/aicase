#!/usr/bin/env bash
# One-time provisioning on the dedicated Debian 12 production host.
# --prepare-only provisions the runtime while DNS is being configured.
set -Eeuo pipefail
umask 027
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 2; }
[[ ${1:-} == '' || ${1:-} == --prepare-only ]] || exit 2
cd "$(dirname "$0")"
domain=popomo.chunpat.cc
state=/var/lib/aicase-prod
config=/etc/aicase-prod
vhost=/www/server/panel/vhost/nginx/aicase-prod.conf
# shellcheck source=/dev/null
source /etc/os-release
[[ $ID == debian && $VERSION_ID == 12 ]] || { echo 'Expected Debian 12.' >&2; exit 1; }
if [[ -f "$vhost" ]] && ! grep -q '^# Managed by aicase production bootstrap' "$vhost"; then
    echo 'Refusing to replace an unrelated virtual host.' >&2
    exit 1
fi
# Do not take over a domain already served by another BaoTa site.
if grep -El "server_name[^;]*[[:space:]]${domain//./\\.}([[:space:];])" /www/server/panel/vhost/nginx/*.conf | grep -vFx "$vhost"; then
    echo 'The production domain is already configured in another site.' >&2
    exit 1
fi
nginx -t
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl python3-venv certbot
# Debian 12 ships PostgreSQL 15; pin the required major via the official PGDG repo.
install -d -m 755 /usr/share/postgresql-common/pgdg
curl --fail --silent --show-error https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
chmod 644 /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
printf '%s\n' 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main' \
    > /etc/apt/sources.list.d/aicase-pgdg.list
apt-get update
apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17
systemctl enable --now postgresql
# Refuse another server/version on the application port.
[[ $(runuser -u postgres -- psql -p 5432 -Atc 'SHOW server_version_num') == 17* ]]
id aicase-prod >/dev/null 2>&1 || useradd --system --home-dir "$state" --shell /usr/sbin/nologin aicase-prod
install -d -m 755 /opt/aicase-prod /opt/aicase-prod/releases "$state" "$state/acme"
install -d -m 755 -o aicase-prod -g aicase-prod "$state/media"
install -d -m 700 "$config" "$state/backups" "$state/daily-backups"
python3 - <<'PY'
import base64, os, secrets, subprocess
from pathlib import Path
path = Path('/etc/aicase-prod/backend.env')
def sql(statement):
    return subprocess.check_output(['runuser', '-u', 'postgres', '--', 'psql', '-p', '5432', '-v', 'ON_ERROR_STOP=1', '-At'], input=statement, text=True)
if not path.exists():
    if sql("SELECT 1 FROM pg_roles WHERE rolname='aicase_prod';").strip() or sql("SELECT 1 FROM pg_database WHERE datname='aicase_prod';").strip():
        raise SystemExit('Existing production role/database requires manual configuration; nothing was reset.')
    values = dict(line.split('=', 1) for line in Path('backend.env.example').read_text().splitlines() if line and not line.startswith('#'))
    values['DJANGO_SECRET_KEY'] = secrets.token_urlsafe(64)
    values['POSTGRES_PASSWORD'] = secrets.token_urlsafe(40)
    values['AI_CONFIG_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
        out.write(''.join(f'{key}={value}\n' for key, value in values.items()))
else:
    values = dict(line.split('=', 1) for line in path.read_text().splitlines() if line and not line.startswith('#'))
assert values['POSTGRES_DB'] == values['POSTGRES_USER'] == 'aicase_prod'
if not sql("SELECT 1 FROM pg_roles WHERE rolname='aicase_prod';").strip():
    password = values['POSTGRES_PASSWORD'].replace("'", "''")
    sql(f"CREATE ROLE aicase_prod LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;")
if not sql("SELECT 1 FROM pg_database WHERE datname='aicase_prod';").strip():
    sql('CREATE DATABASE aicase_prod OWNER aicase_prod;')
print('Production database and private configuration are ready.')
PY
install -m 644 aicase-prod.service /etc/systemd/system/
install -m 644 nginx.locations.conf "$config/nginx.locations.conf"
systemctl daemon-reload
systemctl enable aicase-prod
if [[ ! -L /opt/aicase-prod/current ]]; then touch "$state/deploying"; fi
if [[ ! -f "$vhost" ]]; then
    cat > "$vhost" <<'NGINX'
# Managed by aicase production bootstrap
server {
    listen 80;
    server_name popomo.chunpat.cc;
    location ^~ /.well-known/acme-challenge/ { root /var/lib/aicase-prod/acme; }
    location / { return 503; }
}
NGINX
    nginx -t
    nginx -s reload
fi
if [[ ${1:-} == --prepare-only ]]; then
    echo 'Runtime prepared. Configure DNS, then rerun without --prepare-only for HTTPS.'
    exit 0
fi
certbot certonly --webroot -w "$state/acme" -d "$domain" \
    --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring
cp -p "$vhost" "$config/nginx-before-tls.conf"
cat > "$vhost" <<'NGINX'
# Managed by aicase production bootstrap
server {
    listen 80;
    server_name popomo.chunpat.cc;
    location ^~ /.well-known/acme-challenge/ { root /var/lib/aicase-prod/acme; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl;
    server_name popomo.chunpat.cc;
    root /opt/aicase-prod/current/frontend/storefront;
    ssl_certificate /etc/letsencrypt/live/popomo.chunpat.cc/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/popomo.chunpat.cc/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log /www/wwwlogs/aicase-prod.log;
    error_log /www/wwwlogs/aicase-prod.error.log;
    include /etc/aicase-prod/nginx.locations.conf;
}
NGINX
if ! nginx -t; then
    cp -p "$config/nginx-before-tls.conf" "$vhost"
    exit 1
fi
nginx -s reload
install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/aicase-prod-nginx <<'HOOK'
#!/bin/sh
nginx -t && nginx -s reload
HOOK
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/aicase-prod-nginx
systemctl enable --now certbot.timer
echo 'Production host ready for the manual main workflow.'
