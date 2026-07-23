"""add zoom meeting fields to meetings

Revision ID: c6a1f4b83d9e
Revises: b5e8d3fa2c7e
Create Date: 2026-07-16 00:00:05.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6a1f4b83d9e'
down_revision: Union[str, Sequence[str], None] = 'b5e8d3fa2c7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('meetings', sa.Column('zoom_meeting_id', sa.String(length=255), nullable=True))
    op.add_column('meetings', sa.Column('zoom_join_url', sa.String(length=500), nullable=True))
    op.add_column('meetings', sa.Column('zoom_start_url', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('meetings', 'zoom_start_url')
    op.drop_column('meetings', 'zoom_join_url')
    op.drop_column('meetings', 'zoom_meeting_id')
