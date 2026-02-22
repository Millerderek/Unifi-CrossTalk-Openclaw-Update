"""
Activity Log - Payload Normalizers

Converts raw UniFi Access and UniFi Protect webhook payloads
into the unified ActivityEvent schema.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


def _ts_to_dt(ts) -> datetime:
    """Convert a millisecond epoch timestamp to UTC datetime."""
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _iso_to_dt(iso: str) -> datetime:
    """Convert an ISO-8601 string to UTC datetime."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _dedup_id(prefix: str, *parts) -> str:
    """Generate a deterministic deduplication ID."""
    raw = f"{prefix}-" + "-".join(str(p) for p in parts if p)
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


# ─── Access Normalizer ────────────────────────────────────────────────────────

ACCESS_ACTION_MAP = {
    "access.logs.add":             "access_granted",
    "access.logs.denied":          "access_denied",
    "access.door.unlock":          "door_unlocked",
    "access.door.open":            "door_opened",
    "access.door.close":           "door_closed",
    "access.door.held_open":       "door_held_open",
    "access.remote_view.change":   "remote_view_change",
}


def normalize_access(payload: dict) -> Optional[dict]:
    """
    Normalize a UniFi Access webhook payload.

    UniFi Access sends events in two common formats:
      1. {"event": "access.logs.add", "data": {...}}
      2. {"type": "access.logs.add", "data": {...}, "timestamp": ...}
    """
    event_type = payload.get("event") or payload.get("type") or "unknown"
    data = payload.get("data", payload)

    # Timestamp
    ts = data.get("timestamp") or payload.get("timestamp")
    occurred_at = _ts_to_dt(ts) if ts else datetime.now(timezone.utc)

    # Actor
    actor      = data.get("actor", {})
    user_id    = actor.get("id") or data.get("actor_id") or data.get("user_id")
    first      = actor.get("first_name", "")
    last       = actor.get("last_name", "")
    user_name  = actor.get("display_name") or (f"{first} {last}".strip()) or None

    # Location
    door       = data.get("door", {})
    location   = door.get("name") or data.get("door_name") or data.get("location")

    action = ACCESS_ACTION_MAP.get(event_type, event_type.replace(".", "_"))
    event_id = data.get("id") or _dedup_id("acc", user_id, event_type, int(occurred_at.timestamp()))

    return {
        "event_id":       str(event_id),
        "source":         "access",
        "event_type":     "physical_access",
        "raw_event_type": event_type,
        "user_id":        user_id,
        "user_name":      user_name,
        "location":       location,
        "action":         action,
        "metadata_json":  payload,
        "occurred_at":    occurred_at,
    }


# ─── Protect Normalizer ───────────────────────────────────────────────────────

PROTECT_ACTION_MAP = {
    "ring":              "doorbell_ring",
    "motion":            "motion_detected",
    "smartDetectZone":   "smart_detect",
    "smartDetectLine":   "smart_detect",
    "recording":         "recording_event",
    "camera":            "camera_event",
}


def normalize_protect(payload: dict) -> Optional[dict]:
    """
    Normalize a UniFi Protect webhook payload.

    Protect sends WebSocket-style events:
      {"type": "smartDetectZone", "data": {"camera": "...", "smartDetectTypes": ["person"], ...}}
    """
    event_type = payload.get("type") or payload.get("event") or "unknown"
    data = payload.get("data", payload)

    # Timestamp — Protect uses millisecond epoch in "start"
    ts = data.get("start") or data.get("timestamp") or payload.get("timestamp")
    occurred_at = _ts_to_dt(ts) if ts else datetime.now(timezone.utc)

    # Camera identity
    camera_id   = data.get("camera") or data.get("cameraId")
    camera_name = data.get("cameraName") or data.get("camera_name") or camera_id

    # Smart detect types refine the action
    smart_types = data.get("smartDetectTypes", [])
    action = PROTECT_ACTION_MAP.get(event_type, event_type)
    if smart_types:
        action = f"smart_detect:{','.join(smart_types)}"

    event_id = data.get("id") or _dedup_id("prot", camera_id, event_type, int(occurred_at.timestamp()))

    return {
        "event_id":       str(event_id),
        "source":         "protect",
        "event_type":     "video_event",
        "raw_event_type": event_type,
        "user_id":        camera_id,
        "user_name":      camera_name,
        "location":       camera_name or data.get("zone"),
        "action":         action,
        "metadata_json":  payload,
        "occurred_at":    occurred_at,
    }
