#!/usr/bin/env bash
# ============================================================
# Sally Health — vm-01 Lookup API: Mac-side setup orchestrator
# Run this on your Mac (NOT on vm-01).
#
# Prerequisites on Mac:
#   - SSH key that can reach vm-01 (OCI key pair)
#   - Port 22 open in OCI Security List (already open if you SSH'd before)
#
# Usage:
#   chmod +x setup_from_mac.sh
#   ./setup_from_mac.sh
# ============================================================
set -euo pipefail

VM_IP="129.80.132.81"
VM_USER="ubuntu"                    # change if your OCI username differs (opc for Oracle Linux)
SSH_KEY="$HOME/.ssh/id_rsa"         # change to your actual OCI private key path
REMOTE_DIR="/tmp/sally_setup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── helpers ────────────────────────────────────────────────
die()  { echo "[ERROR] $*" >&2; exit 1; }
info() { echo ""; echo "[INFO] $*"; }

# ── 0. Check SSH key exists ────────────────────────────────
[[ -f "$SSH_KEY" ]] || die "SSH key not found at $SSH_KEY. Edit SSH_KEY in this script."

# ── 1. Collect API key ─────────────────────────────────────
echo ""
echo "============================================================"
echo " Sally Health vm-01 Lookup API — Mac Setup Script"
echo "============================================================"
echo ""
echo "Generate a random API key? (y/n)"
read -r yn
if [[ "$yn" == "y" ]]; then
    API_KEY=$(openssl rand -hex 32)
    echo "  Generated: $API_KEY"
    echo "  >>> COPY THIS KEY — you'll need it for Apps Script Script Properties. <<<"
    echo ""
    echo "Press Enter to continue..."
    read -r
else
    echo -n "Paste your API key: "
    read -r API_KEY
fi
[[ -z "$API_KEY" ]] && die "API key cannot be empty."

# ── 2. SSH connectivity check ──────────────────────────────
info "Testing SSH to $VM_USER@$VM_IP ..."
ssh -i "$SSH_KEY" \
    -o ConnectTimeout=10 \
    -o StrictHostKeyChecking=accept-new \
    -o BatchMode=yes \
    "$VM_USER@$VM_IP" "echo 'SSH OK'" \
  || die "Cannot SSH to vm-01. Troubleshoot:
    - Correct SSH key? (SSH_KEY=$SSH_KEY)
    - OCI Security List: TCP port 22 open inbound?
    - VM running? OCI Console -> Compute -> Instances -> Check state
    - Try manually: ssh -i $SSH_KEY $VM_USER@$VM_IP"

# ── 3. Copy files ──────────────────────────────────────────
info "Uploading files to vm-01:$REMOTE_DIR ..."
ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" "mkdir -p $REMOTE_DIR"
scp -i "$SSH_KEY" \
    "$SCRIPT_DIR/01_schema.sql" \
    "$SCRIPT_DIR/app.py" \
    "$SCRIPT_DIR/deploy_vm01.sh" \
    "$VM_USER@$VM_IP:$REMOTE_DIR/"
ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" "chmod +x $REMOTE_DIR/deploy_vm01.sh"
echo "  Files uploaded OK."

# ── 4. Postgres setup ──────────────────────────────────────
info "Setting up Postgres on vm-01 ..."
ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" bash <<'REMOTE'
set -euo pipefail
if ! command -v psql >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y postgresql postgresql-contrib
fi
sudo systemctl enable --now postgresql

# Create sallyhealth DB
if ! sudo -u postgres psql -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw sallyhealth; then
    sudo -u postgres createdb sallyhealth
    echo "  DB 'sallyhealth' created."
else
    echo "  DB 'sallyhealth' already exists."
fi

# Create izzy role
if ! sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='izzy'" 2>/dev/null | grep -q 1; then
    IZZY_PASS="izzy-$(openssl rand -hex 12)"
    sudo -u postgres psql -c "CREATE ROLE izzy WITH LOGIN PASSWORD '$IZZY_PASS';"
    echo "  Role 'izzy' created with temporary password: $IZZY_PASS"
    echo "  ACTION: Change this password after setup with:"
    echo "    sudo -u postgres psql -c \"ALTER ROLE izzy PASSWORD 'your-strong-password';\""
else
    echo "  Role 'izzy' already exists."
fi

sudo -u postgres psql -d sallyhealth -c "GRANT CONNECT ON DATABASE sallyhealth TO izzy;" 2>/dev/null || true
REMOTE

# ── 5. Load schema ─────────────────────────────────────────
info "Loading lookup schema ..."
ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" \
    "sudo -u postgres psql -d sallyhealth -f $REMOTE_DIR/01_schema.sql"

info "Granting permissions to izzy ..."
ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" sudo -u postgres psql -d sallyhealth <<'SQL'
GRANT USAGE ON SCHEMA lookup TO izzy;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA lookup TO izzy;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lookup TO izzy;
ALTER DEFAULT PRIVILEGES IN SCHEMA lookup GRANT SELECT, INSERT, UPDATE ON TABLES TO izzy;
ALTER DEFAULT PRIVILEGES IN SCHEMA lookup GRANT USAGE, SELECT ON SEQUENCES TO izzy;
SQL

# ── 6. Deploy app ──────────────────────────────────────────
info "Running deploy_vm01.sh on vm-01 ..."
ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" \
    "cd $REMOTE_DIR && bash deploy_vm01.sh '$API_KEY'"

# ── 7. Health check ────────────────────────────────────────
info "Waiting for gunicorn to start ..."
sleep 6
info "Health check (via SSH loopback — bypasses OCI firewall) ..."
ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" \
    'curl -sf http://127.0.0.1:8080/api/sh/health && echo " [PASS]"' \
  || {
    echo ""
    echo "[FAIL] Service not responding. Showing last 40 log lines:"
    ssh -i "$SSH_KEY" "$VM_USER@$VM_IP" "journalctl -u sally-lookup -n 40 --no-pager"
    die "Fix the errors above, then re-run this script."
  }

# ── 8. Done ────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " SETUP COMPLETE"
echo "============================================================"
echo ""
echo " API Key : $API_KEY"
echo " Internal: http://127.0.0.1:8080/api/sh/health  (on vm-01)"
echo " Public  : http://$VM_IP/api/sh/health  (after firewall steps below)"
echo ""
echo "------------------------------------------------------------"
echo " REQUIRED MANUAL STEPS"
echo "------------------------------------------------------------"
echo ""
echo " Step 1 — OCI Security List (do this in the OCI web console):"
echo "   Networking -> Virtual Cloud Networks -> your VCN"
echo "   -> Security Lists -> Default Security List -> Add Ingress Rule"
echo "     Source Type : CIDR"
echo "     Source CIDR : 0.0.0.0/0"
echo "     IP Protocol : TCP"
echo "     Dest Port   : 80"
echo "   (Repeat for port 443 when you add HTTPS)"
echo ""
echo " Step 2 — Ubuntu firewall (SSH into vm-01 and run):"
echo "   sudo ufw allow OpenSSH"
echo "   sudo ufw allow 80/tcp"
echo "   sudo ufw allow 443/tcp"
echo "   sudo ufw --force enable"
echo ""
echo " Step 3 — Test public access (after Step 1 & 2):"
echo "   curl http://$VM_IP/api/sh/health"
echo "   Expected: {\"ok\":true,\"patients\":0}"
echo ""
echo " Step 4 — Apps Script Script Properties:"
echo "   Extensions -> Apps Script -> Project Settings -> Script Properties"
echo "   SALLY_API_KEY  = $API_KEY"
echo "   SALLY_BASE_URL = http://$VM_IP"
echo "   (Update to https://yourdomain after certbot)"
echo ""
echo " Step 5 — HTTPS (optional but recommended):"
echo "   Point DNS A record for api.sallyhealth.org -> $VM_IP"
echo "   Then on vm-01: sudo certbot --nginx -d api.sallyhealth.org"
echo ""
echo " Step 6 — Set a strong izzy DB password (on vm-01):"
echo "   sudo -u postgres psql -c \"ALTER ROLE izzy PASSWORD 'new-strong-pass';\""
echo "   Then update /etc/systemd/system/sally-lookup.service:"
echo "     SALLY_DSN=...user=izzy password=new-strong-pass..."
echo "   sudo systemctl daemon-reload && sudo systemctl restart sally-lookup"
echo ""
