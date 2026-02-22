#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# UniFi Toolkit — VPS Setup Script
#
# Provisions a fresh Ubuntu 22.04/24.04 VPS from zero to a running stack.
# Run as root or with sudo privileges.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/.../setup.sh | bash
#   -- or --
#   chmod +x setup.sh && sudo ./setup.sh
#
# What it does:
#   1. Installs Docker + Docker Compose
#   2. Installs Tailscale
#   3. Clones/copies the toolkit repo
#   4. Walks you through .env configuration
#   5. Gets SSL certificate (requires DNS to be pointed first)
#   6. Starts all containers
#   7. Runs database migrations
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

step()  { echo -e "\n${BOLD}${CYAN}▶  $*${NC}"; }
ok()    { echo -e "${GREEN}✓${NC}  $*"; }
info()  { echo -e "${CYAN}ℹ${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
err()   { echo -e "${RED}✗${NC}  $*"; exit 1; }
prompt(){ echo -e "\n${BOLD}$*${NC}"; }

DEPLOY_DIR="/opt/unifi-toolkit"

# ── 0. Root check ─────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo ./setup.sh"
fi

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║       UniFi Toolkit — VPS Setup                  ║"
echo "║       Docker + Tailscale deployment              ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. System packages ────────────────────────────────────────────────────────
step "1/8 — Updating system packages"
apt-get update -qq
apt-get install -y -qq curl git ufw fail2ban

ok "System packages ready"

# ── 2. UFW firewall ───────────────────────────────────────────────────────────
step "2/8 — Configuring firewall"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable
ok "Firewall: SSH + HTTP + HTTPS allowed"

# ── 3. Docker ─────────────────────────────────────────────────────────────────
step "3/8 — Installing Docker"
if command -v docker &>/dev/null; then
    ok "Docker already installed ($(docker --version))"
else
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    ok "Docker installed"
fi

# Compose v2 check
if ! docker compose version &>/dev/null; then
    apt-get install -y -qq docker-compose-plugin
fi
ok "Docker Compose ready ($(docker compose version --short))"

# ── 4. Tailscale ──────────────────────────────────────────────────────────────
step "4/8 — Installing Tailscale"
if command -v tailscale &>/dev/null; then
    ok "Tailscale already installed"
else
    curl -fsSL https://tailscale.com/install.sh | sh
    ok "Tailscale installed"
fi

# ── 5. Application directory ──────────────────────────────────────────────────
step "5/8 — Setting up application directory"
mkdir -p "$DEPLOY_DIR"/{nginx/conf.d,logs/nginx,scripts,alembic/versions}

# Copy files if running from source directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/docker-compose.yml" ]]; then
    cp -r "$SCRIPT_DIR"/. "$DEPLOY_DIR"/
    ok "Files copied from $SCRIPT_DIR"
else
    warn "docker-compose.yml not found next to setup.sh"
    info "Copy your project files to $DEPLOY_DIR manually"
fi

cd "$DEPLOY_DIR"

# ── 6. Environment config ─────────────────────────────────────────────────────
step "6/8 — Configuring environment"

if [[ -f .env ]]; then
    warn ".env already exists — skipping interactive setup"
    info "Edit $DEPLOY_DIR/.env to change configuration"
else
    cp .env.example .env

    prompt "Enter your Tailscale auth key (from tailscale.com/admin/settings/keys):"
    read -r TS_AUTHKEY
    sed -i "s|TS_AUTHKEY=.*|TS_AUTHKEY=${TS_AUTHKEY}|" .env

    prompt "Enter your domain name (e.g. toolkit.yourdomain.com):"
    read -r DOMAIN
    sed -i "s|PUBLIC_URL=.*|PUBLIC_URL=https://${DOMAIN}|" .env

    # Update nginx config with actual domain
    if [[ -f nginx/conf.d/toolkit.conf ]]; then
        sed -i "s|toolkit.yourdomain.com|${DOMAIN}|g" nginx/conf.d/toolkit.conf
    fi

    # Generate secrets
    WH_ACCESS=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    WH_PROTECT=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    SCIM_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|WEBHOOK_SECRET_ACCESS=|WEBHOOK_SECRET_ACCESS=${WH_ACCESS}|" .env
    sed -i "s|WEBHOOK_SECRET_PROTECT=|WEBHOOK_SECRET_PROTECT=${WH_PROTECT}|" .env
    sed -i "s|SCIM_BEARER_TOKEN=|SCIM_BEARER_TOKEN=${SCIM_TOKEN}|" .env

    prompt "Enter your local UniFi controller Tailscale IP (e.g. 100.x.x.x):"
    read -r CTRL_IP
    sed -i "s|UNIFI_CONTROLLER_URL=.*|UNIFI_CONTROLLER_URL=http://${CTRL_IP}|" .env

    prompt "Enter your UniFi admin username:"
    read -r CTRL_USER
    sed -i "s|UNIFI_USERNAME=.*|UNIFI_USERNAME=${CTRL_USER}|" .env

    prompt "Enter your UniFi admin password:"
    read -rs CTRL_PASS
    echo
    sed -i "s|UNIFI_PASSWORD=|UNIFI_PASSWORD=${CTRL_PASS}|" .env

    ok ".env configured"
    info "Webhook secrets and SCIM token auto-generated and saved to .env"
fi

# Show the generated SCIM token
SCIM_TOKEN=$(grep SCIM_BEARER_TOKEN .env | cut -d= -f2)
info "SCIM Bearer Token: ${BOLD}${SCIM_TOKEN}${NC}"
info "  → Configure this in: UniFi Identity Enterprise > SSO Apps > SCIM Connection"

# Show webhook secrets
echo ""
info "Webhook Secrets (configure in UniFi Access/Protect webhook settings):"
info "  Access:  $(grep WEBHOOK_SECRET_ACCESS .env | cut -d= -f2)"
info "  Protect: $(grep WEBHOOK_SECRET_PROTECT .env | cut -d= -f2)"

# ── 7. SSL Certificate ────────────────────────────────────────────────────────
step "7/8 — SSL Certificate"

DOMAIN=$(grep PUBLIC_URL .env | cut -d= -f2 | sed 's|https://||')

echo ""
warn "DNS check: ensure ${DOMAIN} A record points to this server's public IP"
info "This server's public IP: $(curl -s ifconfig.me 2>/dev/null || echo 'unknown')"
echo ""

prompt "Has DNS propagated? Press Enter to attempt cert issuance, or Ctrl+C to skip"
read -r

# Start nginx in HTTP-only mode first (comment out SSL block temporarily)
# We do this by starting with a minimal config
cat > /tmp/nginx-pre-cert.conf << 'NGINXEOF'
server {
    listen 80;
    server_name _;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 "UniFi Toolkit — SSL setup in progress"; add_header Content-Type text/plain; }
}
NGINXEOF

# Temporarily use pre-cert nginx config
cp nginx/conf.d/toolkit.conf nginx/conf.d/toolkit.conf.bak
cat /tmp/nginx-pre-cert.conf > nginx/conf.d/toolkit-temp.conf

# Start just nginx + certbot
docker compose up -d nginx certbot

sleep 5

# Get cert
docker compose run --rm certbot certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email admin@${DOMAIN} \
    --agree-tos \
    --no-eff-email \
    -d ${DOMAIN} \
    --non-interactive && ok "SSL certificate obtained for ${DOMAIN}" \
    || warn "Certificate issuance failed — you can retry with: scripts/get-cert.sh"

# Restore full nginx config
mv nginx/conf.d/toolkit.conf.bak nginx/conf.d/toolkit.conf
rm -f nginx/conf.d/toolkit-temp.conf

# ── 8. Start everything ───────────────────────────────────────────────────────
step "8/8 — Starting all services"
docker compose up -d --build

echo ""
info "Waiting for app to be ready..."
for i in $(seq 1 30); do
    if docker compose exec -T app curl -sf http://localhost:8000/activity/api/health &>/dev/null; then
        ok "App is healthy"
        break
    fi
    sleep 2
done

# Run database migrations
step "Running database migrations"
docker compose exec app alembic upgrade head
ok "Migrations complete"

# ── Done ──────────────────────────────────────────────────────────────────────
DOMAIN=$(grep PUBLIC_URL .env | cut -d= -f2 | sed 's|https://||')

echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  ✅  UniFi Toolkit is running!${NC}"
echo ""
echo -e "  ${BOLD}Dashboard:${NC}  https://${DOMAIN}/activity/"
echo -e "  ${BOLD}Reports:${NC}    https://${DOMAIN}/activity/reports/"
echo -e "  ${BOLD}Health:${NC}     https://${DOMAIN}/activity/api/health"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "    docker compose logs -f app       # App logs"
echo -e "    docker compose logs -f tailscale # Tailscale status"
echo -e "    docker compose restart app       # Restart app"
echo -e "    docker compose exec app alembic upgrade head  # Migrations"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "    1. Configure UniFi Access webhooks → https://${DOMAIN}/activity/webhooks/access"
echo -e "    2. Configure UniFi Protect webhooks → https://${DOMAIN}/activity/webhooks/protect"
echo -e "    3. See INTEGRATION.md for SAML + SCIM setup"
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════${NC}"
