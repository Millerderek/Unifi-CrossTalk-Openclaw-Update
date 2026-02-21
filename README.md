# UniFi Activity Log — UI Toolkit Plugin

A plugin for [UI Toolkit by Crosstalk Solutions](https://github.com/Crosstalk-Solutions/unifi-toolkit) that adds **UniFi Access** (physical door events) and **UniFi Protect** (camera/motion events) logging, correlated into a unified dashboard.

> **Not affiliated with Ubiquiti Inc.** UniFi is a trademark of Ubiquiti Inc.

---

## What This Adds

UI Toolkit already covers UniFi Network (Wi-Fi Stalker, Threat Watch, Network Pulse). This plugin fills the gap:

| Source | Events Captured |
|--------|----------------|
| **UniFi Access** | Door open/close, badge granted/denied, door held open, remote unlock |
| **UniFi Protect** | Motion detection, person/vehicle/package smart detect, doorbell ring, recording events |

Plus a **cross-source correlation engine** — find Access + Protect events that occur within the same 60-second window (e.g. someone badges in and triggers a camera simultaneously).

---

## Features

- 🚪 **Access event logging** — who badged in/out, where, and when
- 📹 **Protect event logging** — motion, smart detections, doorbell rings
- 🔗 **Event correlation** — cross-source events within configurable time windows
- 🔔 **Outbound webhooks** — Slack, Discord, or generic JSON alerts per event type
- 📊 **Live dashboard** — dark-themed, auto-refreshing, filterable event table
- 🤖 **OpenClaw skill** — AI agent queries physical presence context
- 🔒 **Webhook signature verification** — HMAC-SHA256 validation of UniFi payloads

---

## Architecture

```
UniFi Access  ──► POST /activity/webhooks/access  ──┐
UniFi Protect ──► POST /activity/webhooks/protect ──┼──► SQLite ──► Dashboard + Query API
                                                     │
                                                     └──► Slack / Discord alerts
                                                     └──► OpenClaw AI agent context
```

**Public access** is handled by either:
- **Cloudflare Tunnel** — no VPS or firewall changes needed (recommended)
- **VPS + Tailscale** — Nginx reverse proxy over Tailscale mesh VPN

---

## Quick Start

### 1. Prerequisites

- [UI Toolkit](https://github.com/Crosstalk-Solutions/unifi-toolkit) installed and running
- UniFi Access hub and/or UniFi Protect cameras on your network
- Docker + Docker Compose

### 2. Copy the Tool

```bash
# From your unifi-toolkit directory:
cp -r activity_log tools/
cp -r activity_log/templates/activity_log app/templates/
cp alembic_migration.py alembic/versions/xxxx_add_activity_log_tables.py
```

Edit `alembic/versions/xxxx_add_activity_log_tables.py` and set `down_revision` to your current Alembic head:
```bash
docker compose exec unifi-toolkit alembic current
```

### 3. Register in app/main.py

```python
from tools.activity_log.router import register as register_activity_log
from shared.database import get_db

register_activity_log(app, get_db, templates)
```

### 4. Add to run.py

```python
from tools.activity_log import __version__ as activity_log_version
# ...
print(f"  - Activity Log v{activity_log_version}")
```

### 5. Restart

```bash
docker compose restart
docker compose exec unifi-toolkit alembic upgrade head
```

Dashboard at: `http://localhost:8000/activity/`

---

## Exposing Webhooks Publicly

UniFi controllers need to POST events to your machine. Two options:

### Option A: Cloudflare Tunnel (Recommended — free, no VPS)

```bash
# Install cloudflared, then:
cloudflared tunnel login
cloudflared tunnel create unifi-toolkit
cloudflared tunnel route dns unifi-toolkit webhooks.yourdomain.com

# Copy cloudflare/cloudflared-config.yml and edit with your tunnel UUID
sudo cp cloudflare/cloudflared-config.yml /etc/cloudflared/config.yml
sudo cloudflared service install && sudo systemctl start cloudflared
```

### Option B: VPS + Tailscale

```bash
# On local machine AND VPS:
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up

# On VPS — install Nginx, copy config, get SSL cert:
sudo apt install nginx certbot python3-certbot-nginx
sudo cp tailscale/nginx-vps.conf /etc/nginx/sites-available/unifi-toolkit
# Edit nginx-vps.conf: replace 100.x.x.x with your local machine's Tailscale IP
sudo ln -s /etc/nginx/sites-available/unifi-toolkit /etc/nginx/sites-enabled/
sudo certbot --nginx -d toolkit.yourdomain.com
```

See [`INTEGRATION.md`](INTEGRATION.md) and the [Deployment Guide](docs/) for full step-by-step instructions.

---

## Configure UniFi Webhooks

### UniFi Access
1. **Settings → Integrations → Webhooks → + Add**
2. URL: `https://webhooks.yourdomain.com/activity/webhooks/access`
3. Enable: Access Granted, Access Denied, Door Unlock, Door Open, Door Held Open
4. Copy signing secret → `.env`: `WEBHOOK_SECRET_ACCESS=your_secret`

### UniFi Protect
1. **Settings → Notifications → Webhooks → + Add**
2. URL: `https://webhooks.yourdomain.com/activity/webhooks/protect`
3. Enable: Motion, Smart Detection, Doorbell Ring
4. Copy signing secret → `.env`: `WEBHOOK_SECRET_PROTECT=your_secret`

Restart after adding secrets: `docker compose restart`

---

## OpenClaw Integration

Gives your OpenClaw AI agents real-world physical presence context.

```bash
# Install the skill
cp -r openclaw-skill ~/.openclaw/skills/unifi-activity-log
```

Configure in `~/.openclaw/openclaw.json`:
```json
{
  "skills": {
    "entries": {
      "unifi-activity-log": {
        "apiKey": "https://toolkit.yourdomain.com"
      }
    }
  }
}
```

Agent queries it understands:
- *"Who has been in the building today?"*
- *"Were there any access denied events in the last hour?"*
- *"Give me a security briefing"*
- *"Did the front camera detect anyone after 6pm?"*

Skill scripts:
```bash
uv run openclaw-skill/scripts/check_health.py
uv run openclaw-skill/scripts/query_events.py --source access --hours 24
uv run openclaw-skill/scripts/security_brief.py
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/activity/` | GET | Live dashboard |
| `/activity/api/events` | GET | Query events (filters: source, action, user_id, location, since, until) |
| `/activity/api/events/summary` | GET | 24h stats + top users |
| `/activity/api/events/correlate` | GET | Cross-source events within time window |
| `/activity/api/settings` | GET/POST | Webhook notification config |
| `/activity/api/health` | GET | Health check |
| `/activity/webhooks/access` | POST | UniFi Access webhook receiver |
| `/activity/webhooks/protect` | POST | UniFi Protect webhook receiver |

---

## Repository Structure

```
├── activity_log/               # The tool — copy to tools/ in UI Toolkit
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy models
│   ├── normalizers.py          # Access & Protect payload normalizers
│   ├── notifications.py        # Outbound Slack/Discord webhooks
│   ├── router.py               # FastAPI endpoints
│   └── templates/
│       └── activity_log/
│           └── index.html      # Dashboard
├── openclaw-skill/             # OpenClaw AI agent skill
│   ├── SKILL.md
│   └── scripts/
│       ├── query_events.py
│       ├── security_brief.py
│       └── check_health.py
├── cloudflare/
│   ├── cloudflared-config.yml  # Cloudflare Tunnel config
│   └── cloudflared.service     # systemd service
├── tailscale/
│   ├── setup-tailscale.sh      # Tailscale install script
│   ├── nginx-vps.conf          # Nginx reverse proxy config
│   └── nginx-rate-limits.conf
├── alembic_migration.py        # DB migration — copy to alembic/versions/
├── INTEGRATION.md              # Detailed integration instructions
└── README.md
```

---

## Troubleshooting

**No events appearing after webhook test:**
```bash
docker compose logs -f | grep activity
curl https://webhooks.yourdomain.com/activity/api/health
```

**HTTP 401 on webhook POST:** Webhook secret mismatch — verify `WEBHOOK_SECRET_ACCESS` in `.env` matches what UniFi shows.

**Migration errors:**
```bash
docker compose exec unifi-toolkit alembic current
docker compose exec unifi-toolkit alembic stamp head   # if schema already exists
```

**Cloudflare tunnel not connecting:**
```bash
sudo journalctl -u cloudflared -n 50
cloudflared tunnel info unifi-toolkit
```

---

## License

MIT — see [LICENSE](LICENSE)

---

## Credits

Built as a plugin for [UI Toolkit](https://github.com/Crosstalk-Solutions/unifi-toolkit) by [Crosstalk Solutions](https://www.crosstalksolutions.com/).
