# Activity Log — UI Toolkit Integration Guide

This document shows the **exact minimal changes** needed to wire the
`activity_log` tool into an existing UI Toolkit installation.

---

## File & Folder Placement

```
unifi-toolkit/
├── tools/
│   └── activity_log/              ← copy this entire folder here
│       ├── __init__.py
│       ├── models.py
│       ├── normalizers.py
│       ├── notifications.py
│       └── router.py
├── app/
│   └── templates/
│       └── activity_log/          ← copy template folder here
│           └── index.html
└── alembic/
    └── versions/
        └── xxxx_add_activity_log_tables.py   ← copy migration here
```

---

## 1. Alembic Migration

Copy the migration file to `alembic/versions/` then **set `down_revision`**
to your current head revision ID. Find it with:

```bash
docker compose exec unifi-toolkit alembic current
```

Edit the migration file:
```python
down_revision = 'your_current_head_id_here'   # e.g. 'f3a9b2c81d44'
```

Run migrations:
```bash
docker compose exec unifi-toolkit alembic upgrade head
```

---

## 2. `run.py` — Add version import and print

Add alongside the other tool version imports:

```python
# Existing:
from tools.wifi_stalker import __version__ as stalker_version
from tools.threat_watch import __version__ as threat_watch_version
from tools.network_pulse import __version__ as pulse_version

# Add:
from tools.activity_log import __version__ as activity_log_version
```

Add to the startup print block:
```python
# Existing:
print(f"  - Wi-Fi Stalker v{stalker_version}")
print(f"  - Threat Watch v{threat_watch_version}")
print(f"  - Network Pulse v{pulse_version}")

# Add:
print(f"  - Activity Log v{activity_log_version}")
```

Add to the URL block:
```python
# Existing local URLs:
print(f"Wi-Fi Stalker at: http://localhost:{settings.app_port}/stalker/")
print(f"Threat Watch at: http://localhost:{settings.app_port}/threats/")
print(f"Network Pulse at: http://localhost:{settings.app_port}/pulse/")

# Add:
print(f"Activity Log at: http://localhost:{settings.app_port}/activity/")
```

---

## 3. `app/main.py` — Register the router

Find where other tools are registered (look for `include_router` or a
`register` call for stalker/threats) and add alongside them:

```python
# Wherever other tools are registered, add:
from tools.activity_log.router import register as register_activity_log

# Then call it with the same db session and templates your other tools use:
register_activity_log(app, get_db, templates)
```

If UI Toolkit uses a direct `app.include_router()` pattern instead:
```python
from tools.activity_log.router import router as activity_router
app.include_router(activity_router)
```

---

## 4. Navigation — Add link in sidebar/nav

Find your main nav template (likely `app/templates/base.html` or similar)
and add the Activity Log link alongside the other tools:

```html
<!-- Add alongside Wi-Fi Stalker, Threat Watch, Network Pulse links -->
<a href="/activity/" class="nav-link">
  🔭 Activity Log
</a>
```

---

## 5. `.env` — Optional webhook secrets

Add to your `.env` file if you want UniFi to sign its webhook payloads
(recommended for production):

```env
# Optional: webhook signing secrets from UniFi controller
WEBHOOK_SECRET_ACCESS=your_access_webhook_secret
WEBHOOK_SECRET_PROTECT=your_protect_webhook_secret
```

---

## 6. Configure UniFi Webhooks

### UniFi Access
1. Open **UniFi Access → Settings → Webhooks**
2. Add URL: `https://your-domain.com/activity/webhooks/access`
3. Enable events: Access granted, Access denied, Door unlock, Door open/close
4. Copy signing secret → paste as `WEBHOOK_SECRET_ACCESS` in `.env`

### UniFi Protect
1. Open **UniFi Protect → Settings → Notifications → Webhooks**
2. Add URL: `https://your-domain.com/activity/webhooks/protect`
3. Enable: Motion, Smart Detection (person/vehicle), Doorbell ring
4. Copy signing secret → paste as `WEBHOOK_SECRET_PROTECT` in `.env`

---

## 7. `run.py` schema repair — Add activity_log tables

In `run.py`, inside the `_repair_schema()` function, add the activity_log
tables to the schema repair block (handles cases where migrations were skipped):

```python
# Add inside _repair_schema() after the existing table checks:

# activity_events — activity_log tool
_add_missing_columns(cursor, 'activity_events', {
    'ignored': "ignored BOOLEAN NOT NULL DEFAULT 0",
})

# activity_webhook_config — activity_log tool
_add_missing_columns(cursor, 'activity_webhook_config', {
    'event_door_held_open':   "event_door_held_open BOOLEAN DEFAULT 0",
    'event_vehicle_detected': "event_vehicle_detected BOOLEAN DEFAULT 0",
    'event_motion':           "event_motion BOOLEAN DEFAULT 0",
})
```

---

## Verification

After restarting the container:

```bash
# Health check
curl http://localhost:8000/activity/api/health

# Send a test Access event
curl -X POST http://localhost:8000/activity/webhooks/access \
  -H "Content-Type: application/json" \
  -d '{"event":"access.logs.add","data":{"id":"test-1","door_name":"Main Door","timestamp":"'$(date +%s)'000","actor":{"id":"badge-001","display_name":"Test User"}}}'

# Query it back
curl http://localhost:8000/activity/api/events

# View dashboard
open http://localhost:8000/activity/
```
