"""
Activity Log - Database Models

Tables:
  - activity_events       : Normalized events from Access & Protect
  - activity_webhook_config: Per-source webhook notification settings
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text,
    JSON, Index, func
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ActivityEvent(Base):
    """
    Unified event record from UniFi Access or UniFi Protect.
    Network client events are pulled live from the UniFi API for correlation.
    """
    __tablename__ = "activity_events"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    event_id        = Column(String, unique=True, nullable=False)     # Dedup key
    source          = Column(String(16), nullable=False)              # 'access' | 'protect'
    event_type      = Column(String(64), nullable=False)              # Normalized category
    raw_event_type  = Column(String(128))                             # Original from Ubiquiti
    user_id         = Column(String(128))                             # Badge ID or camera ID
    user_name       = Column(String(256))                             # Display name
    location        = Column(String(256))                             # Door name or camera name
    action          = Column(String(128), nullable=False)             # e.g. 'access_granted'
    metadata_json   = Column(JSON, default=dict)                      # Full raw payload
    occurred_at     = Column(DateTime, nullable=False)
    received_at     = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_activity_source",      "source"),
        Index("ix_activity_occurred_at", "occurred_at"),
        Index("ix_activity_user_id",     "user_id"),
        Index("ix_activity_action",      "action"),
        Index("ix_activity_location",    "location"),
    )

    def to_dict(self):
        return {
            "id":             self.id,
            "event_id":       self.event_id,
            "source":         self.source,
            "event_type":     self.event_type,
            "raw_event_type": self.raw_event_type,
            "user_id":        self.user_id,
            "user_name":      self.user_name,
            "location":       self.location,
            "action":         self.action,
            "metadata":       self.metadata_json or {},
            "occurred_at":    self.occurred_at.isoformat() if self.occurred_at else None,
            "received_at":    self.received_at.isoformat() if self.received_at else None,
        }


class ActivityWebhookConfig(Base):
    """
    Outbound webhook configuration for activity notifications.
    Mirrors the pattern used by wifi_stalker and threat_watch.
    """
    __tablename__ = "activity_webhook_config"

    id                       = Column(Integer, primary_key=True, autoincrement=True)
    enabled                  = Column(Boolean, default=False)
    webhook_url              = Column(Text)
    webhook_type             = Column(String(32), default="slack")   # slack | discord | generic
    # Access events
    event_access_granted     = Column(Boolean, default=True)
    event_access_denied      = Column(Boolean, default=True)
    event_door_held_open     = Column(Boolean, default=False)
    # Protect events
    event_person_detected    = Column(Boolean, default=True)
    event_vehicle_detected   = Column(Boolean, default=False)
    event_doorbell_ring      = Column(Boolean, default=True)
    event_motion             = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "id":                    self.id,
            "enabled":               self.enabled,
            "webhook_url":           self.webhook_url,
            "webhook_type":          self.webhook_type,
            "event_access_granted":  self.event_access_granted,
            "event_access_denied":   self.event_access_denied,
            "event_door_held_open":  self.event_door_held_open,
            "event_person_detected": self.event_person_detected,
            "event_vehicle_detected":self.event_vehicle_detected,
            "event_doorbell_ring":   self.event_doorbell_ring,
            "event_motion":          self.event_motion,
        }
