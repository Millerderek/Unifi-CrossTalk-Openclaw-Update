#!/usr/bin/env python3
"""
UniFi Activity Log - Health Check
Verifies the Activity Log API is reachable and returning data.

Usage:
  uv run check_health.py

Environment:
  ACTIVITY_LOG_URL  Base URL of UI Toolkit
"""

import json
import os
import sys
import urllib.request


def main():
    base = os.environ.get("ACTIVITY_LOG_URL", "http://localhost:8000").rstrip("/")
    url  = f"{base}/activity/api/health"

    print(f"Checking Activity Log at: {base}")

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        status = data.get("status", "unknown")
        total  = data.get("total_events", 0)

        if status == "ok":
            print(f"✅ Activity Log is healthy")
            print(f"   Total events stored: {total:,}")
        else:
            print(f"⚠️  Activity Log returned status: {status}")

    except urllib.error.URLError as e:
        print(f"❌ Cannot reach Activity Log: {e.reason}", file=sys.stderr)
        print(f"   Check that UI Toolkit is running at: {base}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
