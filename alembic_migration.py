"""add activity_log tables

Revision ID: a1b2c3d4e5f6
Revises: (set to your current head revision)
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None   # ← Replace with your current alembic head revision ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── activity_events ──────────────────────────────────────────────────────
    op.create_table(
        "activity_events",
        sa.Column("id",             sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("event_id",       sa.String(),     nullable=False, unique=True),
        sa.Column("source",         sa.String(16),   nullable=False),
        sa.Column("event_type",     sa.String(64),   nullable=False),
        sa.Column("raw_event_type", sa.String(128),  nullable=True),
        sa.Column("user_id",        sa.String(128),  nullable=True),
        sa.Column("user_name",      sa.String(256),  nullable=True),
        sa.Column("location",       sa.String(256),  nullable=True),
        sa.Column("action",         sa.String(128),  nullable=False),
        sa.Column("metadata_json",  sa.JSON(),       nullable=True),
        sa.Column("occurred_at",    sa.DateTime(),   nullable=False),
        sa.Column("received_at",    sa.DateTime(),   server_default=sa.func.now()),
    )
    op.create_index("ix_activity_source",      "activity_events", ["source"])
    op.create_index("ix_activity_occurred_at", "activity_events", ["occurred_at"])
    op.create_index("ix_activity_user_id",     "activity_events", ["user_id"])
    op.create_index("ix_activity_action",      "activity_events", ["action"])
    op.create_index("ix_activity_location",    "activity_events", ["location"])

    # ── activity_webhook_config ───────────────────────────────────────────────
    op.create_table(
        "activity_webhook_config",
        sa.Column("id",                      sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("enabled",                 sa.Boolean(),  default=False),
        sa.Column("webhook_url",             sa.Text(),     nullable=True),
        sa.Column("webhook_type",            sa.String(32), default="slack"),
        sa.Column("event_access_granted",    sa.Boolean(),  default=True),
        sa.Column("event_access_denied",     sa.Boolean(),  default=True),
        sa.Column("event_door_held_open",    sa.Boolean(),  default=False),
        sa.Column("event_person_detected",   sa.Boolean(),  default=True),
        sa.Column("event_vehicle_detected",  sa.Boolean(),  default=False),
        sa.Column("event_doorbell_ring",     sa.Boolean(),  default=True),
        sa.Column("event_motion",            sa.Boolean(),  default=False),
    )


def downgrade() -> None:
    op.drop_table("activity_webhook_config")
    op.drop_index("ix_activity_location",    "activity_events")
    op.drop_index("ix_activity_action",      "activity_events")
    op.drop_index("ix_activity_user_id",     "activity_events")
    op.drop_index("ix_activity_occurred_at", "activity_events")
    op.drop_index("ix_activity_source",      "activity_events")
    op.drop_table("activity_events")
