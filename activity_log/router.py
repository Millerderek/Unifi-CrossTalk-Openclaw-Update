"""
Activity Log - FastAPI Router

Endpoints:
  POST /activity/webhooks/access          Receive UniFi Access events
  POST /activity/webhooks/protect         Receive UniFi Protect events
  GET  /activity/                         Dashboard UI
  GET  /activity/api/events               Query events
  GET  /activity/api/events/summary       24h stats
  GET  /activity/api/events/correlate     Cross-source correlation
  GET  /activity/api/settings             Get webhook config
  POST /activity/api/settings             Update webhook config
  GET  /activity/api/health               Health check
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, text, desc
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.future import select

from .models import Base, ActivityEvent, ActivityWebhookConfig
from .normalizers import normalize_access, normalize_protect
from .notifications import send_notification

log = logging.getLogger(__name__)

router = APIRouter(prefix="/activity", tags=["activity_log"])

# ─── DB Setup ─────────────────────────────────────────────────────────────────
# UI Toolkit provides its own shared DB session via shared.database.
# We accept the AsyncSession as a dependency using the same pattern as other tools.
# The get_db dependency is injected at registration time (see register()).

_get_db = None          # set by register()
_templates = None       # set by register()

def get_db_dep():
    return _get_db()

# ─── Webhook Secrets (optional) ───────────────────────────────────────────────

def _verify_sig(body: bytes, header: Optional[str], secret: str) -> bool:
    if not secret:
        return True
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


# ─── DB Helpers ───────────────────────────────────────────────────────────────

async def _store_event(event_data: dict, db: AsyncSession):
    """Insert normalized event, ignore duplicates."""
    existing = await db.execute(
        select(ActivityEvent).where(ActivityEvent.event_id == event_data["event_id"])
    )
    if existing.scalar_one_or_none():
        return  # Dedup

    evt = ActivityEvent(**event_data)
    db.add(evt)
    await db.commit()
    log.info(f"[{event_data['source'].upper()}] {event_data['action']} — "
             f"{event_data.get('user_name') or event_data.get('user_id')} @ {event_data.get('location')}")

    # Outbound notifications
    result = await db.execute(select(ActivityWebhookConfig).limit(1))
    config = result.scalar_one_or_none()
    if config:
        await send_notification(
            {**event_data, "occurred_at": event_data["occurred_at"].isoformat()},
            config
        )


async def _get_or_create_webhook_config(db: AsyncSession) -> ActivityWebhookConfig:
    result = await db.execute(select(ActivityWebhookConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        config = ActivityWebhookConfig()
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


# ─── Webhook Receivers ────────────────────────────────────────────────────────

@router.post("/webhooks/access", summary="UniFi Access webhook receiver")
async def webhook_access(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_dep),
):
    secret = os.getenv("WEBHOOK_SECRET_ACCESS", "")
    body = await request.body()
    sig  = request.headers.get("X-Signature") or request.headers.get("X-Hub-Signature-256")

    if not _verify_sig(body, sig, secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = payload if isinstance(payload, list) else [payload]
    stored = 0
    for raw in events:
        normalized = normalize_access(raw)
        if normalized:
            await _store_event(normalized, db)
            stored += 1

    return {"status": "ok", "received": len(events), "stored": stored}


@router.post("/webhooks/protect", summary="UniFi Protect webhook receiver")
async def webhook_protect(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_dep),
):
    secret = os.getenv("WEBHOOK_SECRET_PROTECT", "")
    body = await request.body()
    sig  = request.headers.get("X-Signature") or request.headers.get("X-Hub-Signature-256")

    if not _verify_sig(body, sig, secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = payload if isinstance(payload, list) else [payload]
    stored = 0
    for raw in events:
        normalized = normalize_protect(raw)
        if normalized:
            await _store_event(normalized, db)
            stored += 1

    return {"status": "ok", "received": len(events), "stored": stored}


# ─── Query API ────────────────────────────────────────────────────────────────

@router.get("/api/events", summary="Query activity events")
async def get_events(
    source:   Optional[str] = Query(None),
    action:   Optional[str] = Query(None),
    user_id:  Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    since:    Optional[str] = Query(None),
    until:    Optional[str] = Query(None),
    limit:    int           = Query(100, le=1000),
    offset:   int           = Query(0),
    db: AsyncSession = Depends(get_db_dep),
):
    q = select(ActivityEvent)

    if source:   q = q.where(ActivityEvent.source == source)
    if action:   q = q.where(ActivityEvent.action.ilike(f"%{action}%"))
    if user_id:  q = q.where(ActivityEvent.user_id.ilike(f"%{user_id}%"))
    if location: q = q.where(ActivityEvent.location.ilike(f"%{location}%"))
    if since:
        q = q.where(ActivityEvent.occurred_at >= datetime.fromisoformat(since))
    if until:
        q = q.where(ActivityEvent.occurred_at <= datetime.fromisoformat(until))

    count_q = select(func.count()).select_from(q.subquery())
    total   = (await db.execute(count_q)).scalar()

    q = q.order_by(desc(ActivityEvent.occurred_at)).offset(offset).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "events": [r.to_dict() for r in rows],
    }


@router.get("/api/events/summary", summary="24h activity summary")
async def get_summary(db: AsyncSession = Depends(get_db_dep)):
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    by_source = await db.execute(
        select(ActivityEvent.source, ActivityEvent.action, func.count().label("count"))
        .where(ActivityEvent.occurred_at >= since_24h)
        .group_by(ActivityEvent.source, ActivityEvent.action)
        .order_by(desc("count"))
    )

    top_users = await db.execute(
        select(ActivityEvent.user_name, ActivityEvent.user_id, func.count().label("event_count"))
        .where(ActivityEvent.occurred_at >= since_24h)
        .where(ActivityEvent.user_id.isnot(None))
        .group_by(ActivityEvent.user_name, ActivityEvent.user_id)
        .order_by(desc("event_count"))
        .limit(10)
    )

    recent = await db.execute(
        select(ActivityEvent)
        .order_by(desc(ActivityEvent.occurred_at))
        .limit(10)
    )

    # Totals per source
    totals = {}
    breakdown = []
    for row in by_source.all():
        totals[row.source] = totals.get(row.source, 0) + row.count
        breakdown.append({"source": row.source, "action": row.action, "count": row.count})

    return {
        "totals_24h":   totals,
        "breakdown":    breakdown,
        "top_users":    [{"user_name": r.user_name, "user_id": r.user_id, "count": r.event_count}
                         for r in top_users.all()],
        "recent_events":[r.to_dict() for r in recent.scalars().all()],
    }


@router.get("/api/events/correlate", summary="Cross-source event correlation")
async def get_correlations(
    window_seconds: int             = Query(60, le=300),
    since:          Optional[str]   = Query(None),
    limit:          int             = Query(50, le=200),
    db:             AsyncSession    = Depends(get_db_dep),
):
    """
    Find Access events that have a Network client event (from UniFi API) within
    `window_seconds`. Returns Access+Protect events grouped by time window.
    """
    since_dt = datetime.fromisoformat(since) if since else datetime.now(timezone.utc) - timedelta(hours=24)

    # Self-join on the activity_events table across different sources
    # SQLite-compatible raw SQL
    sql = text("""
        SELECT
            e1.id            AS anchor_id,
            e1.source        AS anchor_source,
            e1.user_name     AS anchor_user,
            e1.action        AS anchor_action,
            e1.location      AS anchor_location,
            e1.occurred_at   AS anchor_time,
            e2.id            AS related_id,
            e2.source        AS related_source,
            e2.user_name     AS related_user,
            e2.action        AS related_action,
            e2.location      AS related_location,
            e2.occurred_at   AS related_time,
            CAST(
                (julianday(e2.occurred_at) - julianday(e1.occurred_at)) * 86400
            AS INTEGER)      AS seconds_apart
        FROM activity_events e1
        JOIN activity_events e2
            ON e2.id != e1.id
            AND e2.source != e1.source
            AND e2.occurred_at BETWEEN e1.occurred_at
                AND datetime(e1.occurred_at, '+' || :window || ' seconds')
        WHERE e1.occurred_at >= :since
        ORDER BY e1.occurred_at DESC
        LIMIT :limit
    """)

    result = await db.execute(sql, {"window": window_seconds, "since": since_dt, "limit": limit})
    rows = result.mappings().all()

    return {"window_seconds": window_seconds, "correlations": [dict(r) for r in rows]}


# ─── Settings ─────────────────────────────────────────────────────────────────

@router.get("/api/settings", summary="Get webhook notification settings")
async def get_settings(db: AsyncSession = Depends(get_db_dep)):
    config = await _get_or_create_webhook_config(db)
    return config.to_dict()


@router.post("/api/settings", summary="Update webhook notification settings")
async def update_settings(
    request: Request,
    db: AsyncSession = Depends(get_db_dep),
):
    body = await request.json()
    config = await _get_or_create_webhook_config(db)

    allowed = {
        "enabled", "webhook_url", "webhook_type",
        "event_access_granted", "event_access_denied", "event_door_held_open",
        "event_person_detected", "event_vehicle_detected",
        "event_doorbell_ring", "event_motion",
    }
    for key, val in body.items():
        if key in allowed:
            setattr(config, key, val)

    await db.commit()
    await db.refresh(config)
    return config.to_dict()


@router.get("/api/health")
async def health(db: AsyncSession = Depends(get_db_dep)):
    total = (await db.execute(select(func.count()).select_from(ActivityEvent))).scalar()
    return {"status": "ok", "total_events": total}


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    if _templates:
        return _templates.TemplateResponse(
            "activity_log/index.html",
            {"request": request, "title": "Activity Log"}
        )
    return HTMLResponse("<h1>Activity Log</h1><p>Templates not configured.</p>")


# ─── Registration ─────────────────────────────────────────────────────────────

def register(app, get_db_func, templates=None):
    """
    Called from app/main.py to mount this tool into the main FastAPI app.

    Usage in app/main.py:
        from tools.activity_log.router import register as register_activity_log
        from shared.database import get_db
        register_activity_log(app, get_db, templates)
    """
    global _get_db, _templates
    _get_db    = get_db_func
    _templates = templates
    app.include_router(router)
    log.info("✅ Activity Log tool registered at /activity/")
