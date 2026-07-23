"""create notification logs table

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-20 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_detail', sa.Text(), nullable=True),
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
            "channel IN ('email', 'slack', 'whatsapp', 'push')",
            name='ck_notification_logs_channel',
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'updated', 'cancelled', 'test')",
            name='ck_notification_logs_event_type',
        ),
    )
    op.create_index(
        op.f('ix_notification_logs_id'),
        'notification_logs',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_notification_logs_user_id',
        'notification_logs',
        ['user_id'],
        unique=False,
    )
    op.create_index(
        'ix_notification_logs_created_at',
        'notification_logs',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_notification_logs_created_at',
        table_name='notification_logs',
    )
    op.drop_index(
        'ix_notification_logs_user_id',
        table_name='notification_logs',
    )
    op.drop_index(
        op.f('ix_notification_logs_id'),
        table_name='notification_logs',
    )
    op.drop_table('notification_logs')
