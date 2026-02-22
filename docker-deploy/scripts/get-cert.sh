#!/usr/bin/env bash
# get-cert.sh — Obtain or renew SSL certificate
# Run from the deployment directory: ./scripts/get-cert.sh

set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN=$(grep PUBLIC_URL .env | cut -d= -f2 | sed 's|https://||')

echo "Obtaining certificate for: $DOMAIN"
echo "Server public IP: $(curl -s ifconfig.me)"
echo ""

docker compose run --rm certbot certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "admin@${DOMAIN}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}" \
    --non-interactive

echo ""
echo "✓ Certificate obtained. Reloading nginx..."
docker compose exec nginx nginx -s reload
echo "✓ Done. HTTPS is live at https://${DOMAIN}"
