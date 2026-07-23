"""create meeting series table and series columns on meetings

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-20 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_series',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('cadence', sa.String(length=20), nullable=False),
        sa.Column('interval', sa.Integer(), nullable=False),
        sa.Column('occurrence_count', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.ForeignKeyConstraint(['resource_id'], ['resources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "cadence IN ('daily', 'weekly', 'monthly')",
            name='ck_meeting_series_cadence',
        ),
    )
    op.create_index(
        op.f('ix_meeting_series_id'),
        'meeting_series',
        ['id'],
        unique=False,
    )

    op.add_column(
        'meetings',
        sa.Column('series_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'meetings',
        sa.Column('series_sequence', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_meetings_series_id_meeting_series',
        'meetings',
        'meeting_series',
        ['series_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_meetings_series_id',
        'meetings',
        ['series_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_meetings_series_id', table_name='meetings')
    op.drop_constraint(
        'fk_meetings_series_id_meeting_series',
        'meetings',
        type_='foreignkey',
    )
    op.drop_column('meetings', 'series_sequence')
    op.drop_column('meetings', 'series_id')

    op.drop_index(
        op.f('ix_meeting_series_id'),
        table_name='meeting_series',
    )
    op.drop_table('meeting_series')
