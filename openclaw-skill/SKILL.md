---
name: unifi-activity-log
description: >
  Query and monitor UniFi physical activity events (door access, camera detections,
  motion alerts) from the UI Toolkit Activity Log tool. Use when the user asks about
  who entered a building, recent door events, camera detections, access denied alerts,
  or wants to correlate physical access with network activity. Provides real-time
  context about physical presence and security events to OpenClaw agents.
homepage: https://github.com/Crosstalk-Solutions/unifi-toolkit
metadata:
  openclaw:
    emoji: "🔭"
    requires:
      env:
        - ACTIVITY_LOG_URL
    primaryEnv: ACTIVITY_LOG_URL
    optionalEnv:
      - ACTIVITY_LOG_API_KEY
---

# UniFi Activity Log Skill

Query physical access and camera events from the UI Toolkit Activity Log.
This skill gives OpenClaw agents real-world physical context — who is in the
building, what doors were opened, whether a person was detected on camera —
to inform AI decisions and responses.

## Configuration

Set `ACTIVITY_LOG_URL` to your UI Toolkit base URL:

```bash
# Local:
ACTIVITY_LOG_URL=http://localhost:8000

# Via Tailscale VPS or Cloudflare Tunnel:
ACTIVITY_LOG_URL=https://toolkit.yourdomain.com
```

Optional: set `ACTIVITY_LOG_API_KEY` if your deployment has auth enabled.

In `~/.openclaw/openclaw.json`:
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

## What This Skill Does

The skill exposes scripts that OpenClaw agents call to:

- **Check recent access events** — who badged in/out and when
- **Query camera detections** — person/vehicle detections with location
- **Get correlated events** — cross-source events within a time window
- **Monitor access denials** — security alerts for failed badge attempts
- **Summarize current activity** — 24h stats for briefings and reports

## Agent Usage Examples

> "Who has been in the building today?"
> "Were there any access denied events in the last hour?"
> "Did anyone enter the server room after 6pm?"
> "Show me camera detections from the front door in the last 30 minutes"
> "Give me a security briefing for the last 24 hours"

## Scripts

| Script | Purpose |
|--------|---------|
| `query_events.py` | Flexible event query with all filters |
| `recent_access.py` | Quick summary of who's been in the building |
| `security_brief.py` | 24h security summary for agent briefings |
| `check_health.py`  | Verify Activity Log is reachable |
