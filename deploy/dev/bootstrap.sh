#!/usr/bin/env bash
# One-time setup for the dedicated Debian 13 dev host (with BaoTa Nginx).
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 2
cd "$(dirname "$0")"
domain=aicase.chunpat.cc
state=/var/lib/aicase-dev
config=/etc/aicase-dev
vhost=/www/server/panel/vhost/nginx/aicase-dev.conf
if [[ -f "$vhost" ]] && ! grep -q '^# Managed by aicase dev bootstrap' "$vhost"; then
    echo 'Refusing to replace an existing unrelated virtual host.' >&2
    exit 1
fi
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
apt-get update
apt-get install -y --no-install-recommends python3-venv postgresql postgresql-client certbot curl
id aicase-dev >/dev/null 2>&1 || useradd --system --home-dir "$state" --shell /usr/sbin/nologin aicase-dev
install -d -m 755 /opt/aicase-dev /opt/aicase-dev/releases "$state" "$state/acme"
install -d -m 755 -o aicase-dev -g aicase-dev "$state/media"
install -d -m 700 "$config" "$state/backups"
systemctl enable --now postgresql
python3 - <<'PY'
import base64, os, secrets, subprocess
from pathlib import Path
env_path = Path('/etc/aicase-dev/backend.env')
def psql(sql):
    return subprocess.check_output(['runuser', '-u', 'postgres', '--', 'psql', '-v', 'ON_ERROR_STOP=1', '-At'], input=sql, text=True)
if not env_path.exists():
    if psql("SELECT 1 FROM pg_roles WHERE rolname='aicase_dev';").strip():
        raise SystemExit('aicase_dev database role already exists; prepare backend.env manually without resetting its password.')
    values = dict(line.split('=', 1) for line in Path('backend.env.example').read_text().splitlines() if line and not line.startswith('#'))
    values['DJANGO_SECRET_KEY'] = secrets.token_urlsafe(64)
    values['POSTGRES_PASSWORD'] = secrets.token_urlsafe(40)
    values['AI_CONFIG_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    with os.fdopen(os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
        f.write(''.join(f'{key}={value}\n' for key, value in values.items()))
else:
    values = dict(line.split('=', 1) for line in env_path.read_text().splitlines() if line and not line.startswith('#'))
if not psql("SELECT 1 FROM pg_roles WHERE rolname='aicase_dev';").strip():
    password = values['POSTGRES_PASSWORD'].replace("'", "''")
    psql(f"CREATE ROLE aicase_dev LOGIN PASSWORD '{password}';")
if not psql("SELECT 1 FROM pg_database WHERE datname='aicase_dev';").strip():
    psql('CREATE DATABASE aicase_dev OWNER aicase_dev;')
print('Independent dev database and persistent configuration are ready.')
PY
install -m 644 aicase-dev.service /etc/systemd/system/aicase-dev.service
install -m 644 nginx.locations.conf "$config/nginx.locations.conf"
systemctl daemon-reload
systemctl enable aicase-dev
touch "$state/deploying"

if [[ ! -f "$vhost" ]]; then
    cat > "$vhost" <<'NGINX'
# Managed by aicase dev bootstrap
server {
    listen 80;
    server_name aicase.chunpat.cc;
    location ^~ /.well-known/acme-challenge/ { root /var/lib/aicase-dev/acme; }
    location / { return 503; }
}
NGINX
    nginx -t
    nginx -s reload
fi
certbot certonly --webroot -w "$state/acme" -d "$domain" \
    --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring
cat > "$vhost" <<'NGINX'
# Managed by aicase dev bootstrap
server {
    listen 80;
    server_name aicase.chunpat.cc;
    location ^~ /.well-known/acme-challenge/ { root /var/lib/aicase-dev/acme; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl;
    server_name aicase.chunpat.cc;
    ssl_certificate /etc/letsencrypt/live/aicase.chunpat.cc/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aicase.chunpat.cc/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    include /etc/aicase-dev/nginx.locations.conf;
}
NGINX
nginx -t
nginx -s reload
install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/aicase-dev-nginx <<'HOOK'
#!/bin/sh
nginx -t && nginx -s reload
HOOK
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/aicase-dev-nginx
systemctl enable --now certbot.timer
echo 'Dev server ready. Run the dev workflow to publish its first release.'
