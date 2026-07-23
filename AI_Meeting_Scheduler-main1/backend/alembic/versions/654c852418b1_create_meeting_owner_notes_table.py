"""create meeting owner notes table

Revision ID: 654c852418b1
Revises: 6228d5ef8535
Create Date: 2026-07-15 16:28:37.419410

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '654c852418b1'
down_revision: Union[str, Sequence[str], None] = '6228d5ef8535'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_owner_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
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
            ['created_by_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'meeting_id',
            name='uq_meeting_owner_notes_meeting_id',
        ),
    )
    op.create_index(
        op.f('ix_meeting_owner_notes_id'),
        'meeting_owner_notes',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_meeting_owner_notes_id'),
        table_name='meeting_owner_notes',
    )
    op.drop_table('meeting_owner_notes')
