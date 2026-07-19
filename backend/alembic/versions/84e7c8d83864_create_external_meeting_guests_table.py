"""create external meeting guests table

Revision ID: 84e7c8d83864
Revises: e2b3c4d5f6a7
Create Date: 2026-07-09 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84e7c8d83864'
down_revision: Union[str, Sequence[str], None] = 'e2b3c4d5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'external_meeting_guests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'meeting_id',
            'email',
            name='uq_external_meeting_guests_meeting_id_email',
        ),
    )
    op.create_index(
        op.f('ix_external_meeting_guests_id'),
        'external_meeting_guests',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_external_meeting_guests_id'),
        table_name='external_meeting_guests',
    )
    op.drop_table('external_meeting_guests')
