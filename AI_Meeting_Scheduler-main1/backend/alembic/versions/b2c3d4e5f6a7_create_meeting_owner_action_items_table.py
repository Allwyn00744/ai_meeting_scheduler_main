"""create meeting owner action items table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_owner_action_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_note_id', sa.Integer(), nullable=False),
        sa.Column('task', sa.Text(), nullable=False),
        sa.Column('assignee', sa.String(length=255), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=True),
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='Pending',
            nullable=False,
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
            ['meeting_note_id'],
            ['meeting_owner_notes.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_meeting_owner_action_items_id'),
        'meeting_owner_action_items',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_meeting_owner_action_items_id'),
        table_name='meeting_owner_action_items',
    )
    op.drop_table('meeting_owner_action_items')
