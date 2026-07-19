"""create meeting summaries table

Revision ID: f490a1139ffa
Revises: 6c1b8e757cf8
Create Date: 2026-07-09 15:23:24.788432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f490a1139ffa'
down_revision: Union[str, Sequence[str], None] = '6c1b8e757cf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('source_notes_id', sa.Integer(), nullable=True),
        sa.Column('generated_by_id', sa.Integer(), nullable=False),
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
            ['source_notes_id'],
            ['meeting_notes.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['generated_by_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'meeting_id',
            name='uq_meeting_summaries_meeting_id',
        ),
    )
    op.create_index(
        op.f('ix_meeting_summaries_id'),
        'meeting_summaries',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_meeting_summaries_id'),
        table_name='meeting_summaries',
    )
    op.drop_table('meeting_summaries')
