#!/bin/bash
# ─── Tailscale Setup for UniFi Toolkit ───────────────────────────────────────
#
# Run this on BOTH your local machine AND your VPS.
# Tailscale creates a private mesh network between them with no open ports.
#
# Architecture:
#   Local Machine (UI Toolkit :8000) ←── Tailscale VPN ──→ VPS (Nginx reverse proxy)
#                                                                    ↑
#                                                          Public HTTPS :443
#                                                          (UniFi webhooks hit here)

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

print_step() { echo -e "\n${BOLD}${CYAN}[$1]${NC} $2"; }
print_ok()   { echo -e "${GREEN}✓${NC} $1"; }
print_info() { echo -e "${CYAN}ℹ${NC} $1"; }

print_step "1" "Installing Tailscale"
curl -fsSL https://tailscale.com/install.sh | sh
print_ok "Tailscale installed"

print_step "2" "Authenticating with Tailscale"
print_info "A browser window will open (or copy the URL shown)."
print_info "Log in at tailscale.com to authorize this machine."
echo ""
tailscale up --accept-routes

print_step "3" "Getting your Tailscale IP"
TAILSCALE_IP=$(tailscale ip -4)
print_ok "Your Tailscale IP: ${BOLD}${TAILSCALE_IP}${NC}"
echo ""
print_info "Record this IP — you'll need it for Nginx config on the VPS."
echo ""

print_step "4" "Enabling Tailscale on startup"
systemctl enable tailscaled
systemctl start tailscaled
print_ok "Tailscale will start automatically on boot"

echo ""
echo -e "${BOLD}Done! Next steps:${NC}"
echo "  1. Run this script on your VPS too"
echo "  2. On your VPS, configure Nginx to proxy to ${TAILSCALE_IP}:8000"
echo "  3. See tailscale-nginx.conf for the full Nginx config"
echo ""
