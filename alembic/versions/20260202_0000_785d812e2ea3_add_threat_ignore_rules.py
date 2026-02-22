"""Add threat ignore rules table and ignored columns to events

Revision ID: 785d812e2ea3
Revises: 1c2312b85e85
Create Date: 2026-02-02 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '785d812e2ea3'
down_revision: Union[str, None] = '1c2312b85e85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create threats_ignore_rules table
    op.create_table('threats_ignore_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ip_address', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('ignore_high', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('ignore_medium', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('ignore_low', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('match_source', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('match_destination', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('events_ignored', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_matched', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('threats_ignore_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_threats_ignore_rules_ip_address'), ['ip_address'], unique=False)

    # Add ignored columns to threats_events
    with op.batch_alter_table('threats_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ignored', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('ignored_by_rule_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_threats_events_ignored'), ['ignored'], unique=False)


def downgrade() -> None:
    # Remove ignored columns from threats_events
    with op.batch_alter_table('threats_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_threats_events_ignored'))
        batch_op.drop_column('ignored_by_rule_id')
        batch_op.drop_column('ignored')

    # Drop threats_ignore_rules table
    with op.batch_alter_table('threats_ignore_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_threats_ignore_rules_ip_address'))

    op.drop_table('threats_ignore_rules')
