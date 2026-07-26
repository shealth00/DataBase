#!/usr/bin/env bash
# Run ON vm-01 (129.80.132.81). Sets up the lookup API as a systemd service.
# Usage: bash deploy_vm01.sh <API_KEY>
set -euo pipefail

APP_DIR=/opt/sally_lookup
API_KEY="${1:?Usage: bash deploy_vm01.sh <API_KEY>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip nginx certbot python3-certbot-nginx

sudo mkdir -p "$APP_DIR"
sudo cp "$SCRIPT_DIR/app.py" "$APP_DIR"/
cd "$APP_DIR"
sudo python3 -m venv venv
sudo ./venv/bin/pip install -q flask flask-cors "psycopg[binary]" gunicorn

# Load schema
if command -v psql >/dev/null; then
  psql -d sallyhealth -f "$SCRIPT_DIR/01_schema.sql" && echo "Schema loaded OK" \
    || echo "[WARN] Run manually: psql -d sallyhealth -f 01_schema.sql"
fi

sudo tee /etc/systemd/system/sally-lookup.service >/dev/null <<UNIT
[Unit]
Description=Sally Health Patient Lookup API
After=network.target postgresql.service

[Service]
User=izzy
WorkingDirectory=$APP_DIR
Environment="SALLY_DSN=host=127.0.0.1 port=5432 dbname=sallyhealth user=izzy options='-c search_path=lookup,public'"
Environment="SALLY_API_KEY=$API_KEY"
ExecStart=$APP_DIR/venv/bin/gunicorn -w 3 -b 127.0.0.1:8080 --timeout 60 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now sally-lookup

sudo tee /etc/nginx/sites-available/sally-lookup >/dev/null <<'NGINX'
server {
    listen 80;
    server_name _;
    location /api/sh/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/sally-lookup /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo ""
echo "Done. Internal test: curl http://127.0.0.1:8080/api/sh/health"
echo ""
echo "MANUAL STEPS REQUIRED:"
echo "  1. OCI Console -> Networking -> VCN -> Security Lists -> Add Ingress Rule"
echo "     Source: 0.0.0.0/0  Protocol: TCP  Port: 80  (and 443 for HTTPS)"
echo "  2. sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw --force enable"
echo "  3. Public test: curl http://129.80.132.81/api/sh/health"
echo "  4. HTTPS: sudo certbot --nginx -d api.sallyhealth.org"
