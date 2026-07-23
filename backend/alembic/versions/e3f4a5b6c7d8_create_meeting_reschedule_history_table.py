"""create meeting reschedule history table

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-20 09:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_reschedule_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('previous_start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('previous_end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('new_start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('new_end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rescheduled_by_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['meeting_id'],
            ['meetings.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['rescheduled_by_id'],
            ['users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_meeting_reschedule_history_id'),
        'meeting_reschedule_history',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_meeting_reschedule_history_meeting_id',
        'meeting_reschedule_history',
        ['meeting_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_meeting_reschedule_history_meeting_id',
        table_name='meeting_reschedule_history',
    )
    op.drop_index(
        op.f('ix_meeting_reschedule_history_id'),
        table_name='meeting_reschedule_history',
    )
    op.drop_table('meeting_reschedule_history')
