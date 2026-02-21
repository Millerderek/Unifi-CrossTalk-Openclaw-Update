"""
Activity Log - Outbound Webhook Notifications

Sends formatted alerts to Slack, Discord, or generic webhooks
when activity events match configured notification rules.
"""

import logging
from datetime import datetime
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

# Source badge colors
SOURCE_COLORS = {
    "access":  "#238636",   # Green
    "protect": "#d29922",   # Amber
}

# Action emoji map
ACTION_EMOJI = {
    "access_granted":      "✅",
    "access_denied":       "🚫",
    "door_unlocked":       "🔓",
    "door_opened":         "🚪",
    "door_closed":         "🚪",
    "door_held_open":      "⚠️",
    "doorbell_ring":       "🔔",
    "motion_detected":     "👁️",
    "smart_detect:person": "🧍",
    "smart_detect:vehicle":"🚗",
    "recording_event":     "🎥",
}


def _should_notify(event: dict, config) -> bool:
    """Check whether this event matches the notification config."""
    if not config or not config.enabled or not config.webhook_url:
        return False

    action = event.get("action", "")
    source = event.get("source", "")

    if source == "access":
        if action == "access_granted"  and config.event_access_granted:   return True
        if action == "access_denied"   and config.event_access_denied:    return True
        if action == "door_held_open"  and config.event_door_held_open:   return True

    if source == "protect":
        if action == "doorbell_ring"             and config.event_doorbell_ring:    return True
        if action == "motion_detected"           and config.event_motion:           return True
        if "person"  in action                   and config.event_person_detected:  return True
        if "vehicle" in action                   and config.event_vehicle_detected: return True

    return False


def _format_slack(event: dict) -> dict:
    action   = event.get("action", "event")
    source   = event.get("source", "")
    user     = event.get("user_name") or event.get("user_id") or "Unknown"
    location = event.get("location") or "Unknown"
    emoji    = ACTION_EMOJI.get(action, "📋")
    color    = SOURCE_COLORS.get(source, "#8b949e")
    ts       = event.get("occurred_at", "")

    return {
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{action.replace('_', ' ').title()}*\n"
                                f">*Who:* {user}\n"
                                f">*Where:* {location}\n"
                                f">*Source:* {source.title()}\n"
                                f">*When:* {ts}"
                    }
                }
            ]
        }]
    }


def _format_discord(event: dict) -> dict:
    action   = event.get("action", "event")
    source   = event.get("source", "")
    user     = event.get("user_name") or event.get("user_id") or "Unknown"
    location = event.get("location") or "Unknown"
    emoji    = ACTION_EMOJI.get(action, "📋")

    color_int = {
        "access":  0x238636,
        "protect": 0xd29922,
    }.get(source, 0x8b949e)

    return {
        "embeds": [{
            "title":       f"{emoji} {action.replace('_', ' ').title()}",
            "color":       color_int,
            "fields": [
                {"name": "Who",    "value": user,           "inline": True},
                {"name": "Where",  "value": location,       "inline": True},
                {"name": "Source", "value": source.title(), "inline": True},
            ],
            "timestamp": event.get("occurred_at"),
        }]
    }


def _format_generic(event: dict) -> dict:
    return {
        "event_id":   event.get("event_id"),
        "source":     event.get("source"),
        "action":     event.get("action"),
        "user_name":  event.get("user_name"),
        "user_id":    event.get("user_id"),
        "location":   event.get("location"),
        "occurred_at":event.get("occurred_at"),
    }


async def send_notification(event: dict, config) -> bool:
    """Send outbound webhook notification if the event matches config rules."""
    if not _should_notify(event, config):
        return False

    wtype = (config.webhook_type or "generic").lower()
    if wtype == "slack":
        payload = _format_slack(event)
    elif wtype == "discord":
        payload = _format_discord(event)
    else:
        payload = _format_generic(event)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status < 300:
                    log.debug(f"Webhook sent for {event.get('action')} → HTTP {resp.status}")
                    return True
                else:
                    body = await resp.text()
                    log.warning(f"Webhook HTTP {resp.status}: {body[:200]}")
                    return False
    except Exception as e:
        log.error(f"Webhook delivery failed: {e}")
        return False
