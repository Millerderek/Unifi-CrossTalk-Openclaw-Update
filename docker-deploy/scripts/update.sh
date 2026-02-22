#!/usr/bin/env bash
# update.sh — Update the toolkit to latest version
# Usage: ./scripts/update.sh

set -euo pipefail
cd "$(dirname "$0")/.."

echo "▶  Pulling latest images and rebuilding app..."
docker compose pull nginx certbot tailscale
docker compose build app

echo "▶  Running migrations..."
docker compose run --rm app alembic upgrade head

echo "▶  Restarting app..."
docker compose up -d --no-deps app

echo "▶  Reloading nginx..."
docker compose exec nginx nginx -s reload

echo ""
echo "✓  Update complete."
docker compose ps
