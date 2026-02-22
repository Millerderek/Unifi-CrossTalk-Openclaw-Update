# VPS Deployment Guide — Docker + Tailscale

## Architecture

```
Internet
    │
    ▼ port 443 (HTTPS)
┌─────────────────────────────────────────────────┐
│  VPS (public IP)                                │
│                                                 │
│  ┌──────────┐    ┌──────────┐   ┌───────────┐  │
│  │  Nginx   │───►│ Toolkit  │   │ Tailscale │  │
│  │  :443    │    │ app :8000│   │  sidecar  │  │
│  └──────────┘    └──────────┘   └─────┬─────┘  │
│        │               │              │         │
│  Certbot               │         Tailnet VPN    │
│  (auto SSL)            │              │         │
└────────────────────────┼──────────────┼─────────┘
                         │              │
                         └──────────────►
                                        │
                         ┌──────────────▼──────────┐
                         │  Your Local Network      │
                         │  UniFi Dream Machine     │
                         │  UniFi Access            │
                         │  UniFi Protect           │
                         └─────────────────────────┘
```

**Key points:**
- No inbound ports on your local network — Tailscale is outbound-only from both ends
- Nginx handles public HTTPS and routes webhooks + SAML + SCIM separately
- App container shares Tailscale's network namespace — sees local Tailnet IPs directly
- SQLite lives in a Docker volume — survives container restarts and updates

---

## Prerequisites

| Item | Notes |
|------|-------|
| VPS | Ubuntu 22.04 or 24.04, minimum 1 vCPU / 1GB RAM |
| Domain | A record pointing to VPS public IP |
| Tailscale account | Free tier is fine — create at tailscale.com |
| Local UniFi console | Dream Machine, UDM-Pro, or CloudKey running UniFi OS |

---

## Step 1: Provision the VPS

Any provider works — DigitalOcean, Hetzner, Linode, Vultr. Minimum $5/mo droplet.

After creating the VPS, note its public IP and point your domain A record to it:
```
toolkit.yourdomain.com  →  A  →  <VPS public IP>
```

Allow DNS to propagate before Step 4.

---

## Step 2: Copy files to VPS

```bash
# From your local machine:
scp -r docker-deploy/ root@<VPS-IP>:/opt/unifi-toolkit/

# SSH in:
ssh root@<VPS-IP>
cd /opt/unifi-toolkit
```

---

## Step 3: Run the setup script

```bash
chmod +x scripts/setup.sh
sudo ./scripts/setup.sh
```

The script handles everything: Docker install, Tailscale install, .env config, cert issuance, and container startup. It will prompt you for:

- **Tailscale auth key** — create at [tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys)
  - Type: Auth key
  - Reusable: yes
  - Ephemeral: yes (VPS will be removed from tailnet if containers stop)
  - Tag: `tag:vps`

- **Domain name** — `toolkit.yourdomain.com`

- **Local UniFi controller Tailscale IP** — run `tailscale ip -4` on your Dream Machine or local machine where UniFi runs

- **UniFi admin credentials**

### Manual setup (if you prefer not to run the script)

```bash
# 1. Configure env
cp .env.example .env
nano .env   # fill in TS_AUTHKEY, PUBLIC_URL, UNIFI_* vars

# 2. Update domain in nginx config
sed -i 's/toolkit.yourdomain.com/YOUR_DOMAIN/g' nginx/conf.d/toolkit.conf

# 3. Start nginx + certbot only (HTTP mode, for cert issuance)
docker compose up -d nginx certbot

# 4. Get SSL cert
./scripts/get-cert.sh

# 5. Start everything
docker compose up -d --build

# 6. Run migrations
docker compose exec app alembic upgrade head
```

---

## Step 4: Authorize Tailscale on local machine

On your **local machine** (where UniFi runs, or where you already have Tailscale):

```bash
# Install Tailscale if not already installed:
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
```

Then verify connectivity from the VPS:
```bash
# On VPS:
docker compose exec tailscale tailscale status
docker compose exec tailscale ping 100.x.x.x   # your local machine's Tailscale IP
```

---

## Step 5: Configure UniFi webhooks

Point your UniFi controllers at the VPS.

**UniFi Access:**
```
Webhook URL: https://toolkit.yourdomain.com/activity/webhooks/access
Secret:      <value of WEBHOOK_SECRET_ACCESS from .env>
```

**UniFi Protect:**
```
Webhook URL: https://toolkit.yourdomain.com/activity/webhooks/protect
Secret:      <value of WEBHOOK_SECRET_PROTECT from .env>
```

Test from VPS:
```bash
curl -X POST https://toolkit.yourdomain.com/activity/webhooks/access \
  -H "Content-Type: application/json" \
  -d '{"event":"test"}'
# Should return 200 or 422 (not 502 or 404)
```

---

## Step 6: Verify everything is running

```bash
# All services healthy?
docker compose ps

# App responding?
curl https://toolkit.yourdomain.com/activity/api/health

# Tailscale connected?
docker compose exec tailscale tailscale status

# Live logs:
docker compose logs -f app
```

---

## Optional: Configure SAML SSO + SCIM

See `FABRICS_INTEGRATION.md` for the full walkthrough. TL;DR:

1. Add SAML values to `.env`
2. `docker compose restart app`
3. Visit `https://toolkit.yourdomain.com/auth/saml/login`

---

## Ongoing operations

### Update the application
```bash
cd /opt/unifi-toolkit
./scripts/update.sh
```

### Backup the database
```bash
./scripts/backup.sh /var/backups/toolkit
```

Add to cron for nightly backups:
```bash
crontab -e
# Add:
0 2 * * * /opt/unifi-toolkit/scripts/backup.sh /var/backups/toolkit
```

### View logs
```bash
docker compose logs -f app        # App logs
docker compose logs -f nginx      # Nginx access/error
docker compose logs -f tailscale  # Tailscale VPN
```

### Restart a service
```bash
docker compose restart app
docker compose restart nginx
```

### Check Tailscale connectivity
```bash
docker compose exec tailscale tailscale status
docker compose exec tailscale tailscale ping 100.x.x.x
```

### Run a migration manually
```bash
docker compose exec app alembic upgrade head
docker compose exec app alembic current   # show current revision
docker compose exec app alembic history   # show all migrations
```

### Get a shell in the app container
```bash
docker compose exec app bash
```

---

## Troubleshooting

### 502 Bad Gateway
Nginx can reach the container but the app isn't responding.
```bash
docker compose ps app              # Is it running?
docker compose logs --tail=50 app  # What error?
curl http://localhost:8000/activity/api/health  # Direct check (from VPS host)
```

### Tailscale not connecting to local network
```bash
docker compose logs tailscale      # Auth error? Key expired?
docker compose exec tailscale tailscale status
# Re-auth if needed:
docker compose exec tailscale tailscale up --authkey <new-key>
```

### SSL certificate errors
```bash
docker compose logs certbot
./scripts/get-cert.sh              # Re-attempt issuance
# Ensure DNS A record is set and propagated before retrying
```

### Webhook events not arriving
```bash
# Test from UniFi controller — webhook URL must be publicly reachable
curl -I https://toolkit.yourdomain.com/activity/webhooks/access
# Check rate limiting — 60/min default
docker compose logs nginx | grep "limiting"
```

### App won't start after migration
```bash
docker compose exec app alembic history   # check migration chain
docker compose exec app alembic current   # see where it stopped
docker compose exec app alembic upgrade head  # retry
```
