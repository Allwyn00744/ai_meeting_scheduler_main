"""create analytics events table

Revision ID: 6228d5ef8535
Revises: 48c6e30c9e61
Create Date: 2026-07-10 00:13:39.055477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6228d5ef8535'
down_revision: Union[str, Sequence[str], None] = '48c6e30c9e61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'analytics_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['meeting_id'],
            ['meetings.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "event_type IN ("
            "'CONFLICT_BLOCKED_OWNER', "
            "'CONFLICT_BLOCKED_PARTICIPANT', "
            "'CONFLICT_BLOCKED_RESOURCE'"
            ")",
            name='ck_analytics_events_event_type',
        ),
    )
    op.create_index(
        op.f('ix_analytics_events_id'),
        'analytics_events',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_analytics_events_user_id',
        'analytics_events',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_analytics_events_user_id',
        table_name='analytics_events',
    )
    op.drop_index(
        op.f('ix_analytics_events_id'),
        table_name='analytics_events',
    )
    op.drop_table('analytics_events')
