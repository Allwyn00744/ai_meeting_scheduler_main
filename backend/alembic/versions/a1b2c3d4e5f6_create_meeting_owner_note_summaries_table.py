"""create meeting owner note summaries table

Revision ID: a1b2c3d4e5f6
Revises: 654c852418b1
Create Date: 2026-07-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '654c852418b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_owner_note_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_note_id', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
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
        sa.UniqueConstraint(
            'meeting_note_id',
            name='uq_meeting_owner_note_summaries_meeting_note_id',
        ),
    )
    op.create_index(
        op.f('ix_meeting_owner_note_summaries_id'),
        'meeting_owner_note_summaries',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_meeting_owner_note_summaries_id'),
        table_name='meeting_owner_note_summaries',
    )
    op.drop_table('meeting_owner_note_summaries')
