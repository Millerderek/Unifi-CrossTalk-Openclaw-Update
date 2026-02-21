#!/usr/bin/env python3
"""
UniFi Activity Log - Security Briefing
OpenClaw skill script: generate a structured 24h security summary
suitable for injecting into agent context or morning briefings.

Usage:
  uv run security_brief.py [--hours 24] [--format text|json]

Environment:
  ACTIVITY_LOG_URL      Base URL of UI Toolkit
  ACTIVITY_LOG_API_KEY  Optional: bearer token if auth enabled
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta


def get_headers():
    h = {"Accept": "application/json"}
    key = os.environ.get("ACTIVITY_LOG_API_KEY")
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def fetch(url):
    try:
        req = urllib.request.Request(url, headers=get_headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"ERROR fetching {url}: {e}", file=sys.stderr)
        return {}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours",  type=int, default=24)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    base = os.environ.get("ACTIVITY_LOG_URL", "http://localhost:8000").rstrip("/")

    # Fetch summary stats
    summary = fetch(f"{base}/activity/api/events/summary")
    totals  = summary.get("totals_24h", {})
    breakdown = summary.get("breakdown", [])
    top_users = summary.get("top_users", [])

    # Fetch recent denied events
    denied_url = f"{base}/activity/api/events?source=access&action=denied&limit=10"
    denied_resp = fetch(denied_url)
    denied_events = denied_resp.get("events", [])

    # Fetch recent person detections
    person_url = f"{base}/activity/api/events?source=protect&action=person&limit=10"
    person_resp = fetch(person_url)
    person_events = person_resp.get("events", [])

    # Fetch correlations (potential tailgating / badge+camera combos)
    corr_url = f"{base}/activity/api/events/correlate?window_seconds=60&limit=5"
    corr_resp = fetch(corr_url)
    correlations = corr_resp.get("correlations", [])

    def fmt_ts(iso):
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return iso or "?"

    now = datetime.now(timezone.utc)

    if args.format == "json":
        print(json.dumps({
            "generated_at": now.isoformat(),
            "window_hours": args.hours,
            "totals": totals,
            "access_denied_count": len(denied_events),
            "person_detections": len(person_events),
            "top_users": top_users[:5],
            "denied_events": denied_events[:5],
            "person_detections_detail": person_events[:5],
            "correlations": correlations[:3],
        }, indent=2, default=str))
        return

    # ── Human/Agent-readable text output ─────────────────────────────────────
    sep = "─" * 60
    print(f"\n🔭 UniFi Activity Log — Security Briefing")
    print(f"   Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}  |  Window: Last {args.hours}h")
    print(sep)

    # Summary totals
    print("\n📊 Event Totals (24h)")
    print(f"   Access events  : {totals.get('access', 0)}")
    print(f"   Protect events : {totals.get('protect', 0)}")
    total_all = sum(totals.values())
    print(f"   Total          : {total_all}")

    # Denied access
    denied_total = sum(b["count"] for b in breakdown if b["action"] == "access_denied")
    status = "⚠️  ATTENTION" if denied_total > 0 else "✅ Clear"
    print(f"\n🚫 Access Denied  ({status}: {denied_total} incidents)")
    if denied_events:
        for e in denied_events[:5]:
            user = e.get("user_name") or e.get("user_id") or "Unknown"
            loc  = e.get("location") or "?"
            print(f"   {fmt_ts(e.get('occurred_at'))}  {user:30s}  @ {loc}")
    else:
        print("   No denied events")

    # Person detections
    person_total = sum(b["count"] for b in breakdown if "person" in (b.get("action") or ""))
    print(f"\n🧍 Person Detections  ({person_total} total)")
    if person_events:
        for e in person_events[:5]:
            cam = e.get("user_name") or e.get("location") or "?"
            print(f"   {fmt_ts(e.get('occurred_at'))}  Camera: {cam}")
    else:
        print("   No person detections")

    # Top users
    print(f"\n👥 Most Active Users (24h)")
    if top_users:
        for u in top_users[:5]:
            name = u.get("user_name") or u.get("user_id") or "Unknown"
            print(f"   {name:40s}  {u.get('count', 0)} events")
    else:
        print("   No user data")

    # Correlations
    if correlations:
        print(f"\n🔗 Cross-Source Correlations (within 60s windows)")
        for c in correlations[:3]:
            print(f"   {c.get('anchor_source','?').upper()} {c.get('anchor_action','?')} "
                  f"← {int(c.get('seconds_apart',0))}s → "
                  f"{c.get('related_source','?').upper()} {c.get('related_action','?')}")
    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
