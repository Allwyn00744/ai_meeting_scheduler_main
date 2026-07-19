"""create meeting owner insights table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-16 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_owner_insights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_note_id', sa.Integer(), nullable=False),
        sa.Column('key_points_json', sa.JSON(), nullable=False),
        sa.Column('decisions_json', sa.JSON(), nullable=False),
        sa.Column('risks_json', sa.JSON(), nullable=False),
        sa.Column('next_steps_json', sa.JSON(), nullable=False),
        sa.Column('overall_status', sa.String(length=20), nullable=False),
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
            name='uq_meeting_owner_insights_meeting_note_id',
        ),
    )
    op.create_index(
        op.f('ix_meeting_owner_insights_id'),
        'meeting_owner_insights',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_meeting_owner_insights_id'),
        table_name='meeting_owner_insights',
    )
    op.drop_table('meeting_owner_insights')
