"""add outlook event fields to meetings

Revision ID: 5878d3150ab3
Revises: 4cb8f2eaeda4
Create Date: 2026-07-16 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5878d3150ab3'
down_revision: Union[str, Sequence[str], None] = '4cb8f2eaeda4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('meetings', sa.Column('outlook_event_id', sa.String(length=255), nullable=True))
    op.add_column('meetings', sa.Column('outlook_event_link', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('meetings', 'outlook_event_link')
    op.drop_column('meetings', 'outlook_event_id')
