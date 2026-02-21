#!/usr/bin/env python3
"""
UniFi Activity Log - Query Events
OpenClaw skill script: query Access and Protect events with filters.

Usage (OpenClaw will call this with env vars set):
  uv run query_events.py [--source access|protect] [--action granted|denied|person]
                          [--location "Main Door"] [--hours 24] [--limit 20]

Environment:
  ACTIVITY_LOG_URL      Base URL of UI Toolkit (e.g. https://toolkit.yourdomain.com)
  ACTIVITY_LOG_API_KEY  Optional: bearer token if auth is enabled
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta


def get_headers():
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = os.environ.get("ACTIVITY_LOG_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def query_events(base_url, source=None, action=None, location=None,
                 user=None, hours=24, limit=50):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    params = {"limit": limit, "since": since}
    if source:   params["source"]   = source
    if action:   params["action"]   = action
    if location: params["location"] = location
    if user:     params["user_id"]  = user

    url = f"{base_url.rstrip('/')}/activity/api/events?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers=get_headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: HTTP {e.code} — {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def format_event(e):
    """Format a single event for agent-readable output."""
    ts = e.get("occurred_at", "")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        ts = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        pass

    source   = e.get("source", "?").upper()
    action   = e.get("action", "?").replace("_", " ")
    user     = e.get("user_name") or e.get("user_id") or "Unknown"
    location = e.get("location") or "Unknown location"

    return f"[{ts}] [{source}] {action} — {user} @ {location}"


def main():
    parser = argparse.ArgumentParser(description="Query UniFi Activity Log events")
    parser.add_argument("--source",   choices=["access", "protect"], help="Filter by source")
    parser.add_argument("--action",   help="Filter by action (partial match)")
    parser.add_argument("--location", help="Filter by location (door/camera name)")
    parser.add_argument("--user",     help="Filter by user name or MAC/badge ID")
    parser.add_argument("--hours",    type=int, default=24, help="Look back N hours (default: 24)")
    parser.add_argument("--limit",    type=int, default=50,  help="Max results (default: 50)")
    parser.add_argument("--json",     action="store_true",   help="Output raw JSON")
    args = parser.parse_args()

    base_url = os.environ.get("ACTIVITY_LOG_URL", "http://localhost:8000")
    result   = query_events(base_url, args.source, args.action,
                            args.location, args.user, args.hours, args.limit)

    events = result.get("events", [])
    total  = result.get("total", 0)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    # Agent-friendly text output
    print(f"Activity Log Query Results")
    print(f"  Total matching: {total}  |  Showing: {len(events)}  |  Window: last {args.hours}h")
    print("=" * 70)

    if not events:
        print("No events found matching your filters.")
        return

    for e in events:
        print(format_event(e))

    if total > len(events):
        print(f"\n... and {total - len(events)} more. Use --limit to see more.")


if __name__ == "__main__":
    main()
