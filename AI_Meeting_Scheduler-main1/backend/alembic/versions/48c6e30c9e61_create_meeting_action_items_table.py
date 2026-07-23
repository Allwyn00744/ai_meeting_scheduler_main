"""create meeting action items table

Revision ID: 48c6e30c9e61
Revises: f490a1139ffa
Create Date: 2026-07-09 15:23:37.601074

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48c6e30c9e61'
down_revision: Union[str, Sequence[str], None] = 'f490a1139ffa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_action_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('summary_id', sa.Integer(), nullable=False),
        sa.Column('task', sa.Text(), nullable=False),
        sa.Column('assignee', sa.String(length=255), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column(
            'status',
            sa.String(length=20),
            nullable=False,
            server_default='pending',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
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
            ['summary_id'],
            ['meeting_summaries.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'completed')",
            name='ck_meeting_action_items_status',
        ),
    )
    op.create_index(
        op.f('ix_meeting_action_items_id'),
        'meeting_action_items',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_meeting_action_items_meeting_id',
        'meeting_action_items',
        ['meeting_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_meeting_action_items_meeting_id',
        table_name='meeting_action_items',
    )
    op.drop_index(
        op.f('ix_meeting_action_items_id'),
        table_name='meeting_action_items',
    )
    op.drop_table('meeting_action_items')
