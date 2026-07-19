"""add teams join url to meetings

Revision ID: d00d72ef899c
Revises: c6a1f4b83d9e
Create Date: 2026-07-16 00:00:06.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd00d72ef899c'
down_revision: Union[str, Sequence[str], None] = 'c6a1f4b83d9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('meetings', sa.Column('teams_join_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('meetings', 'teams_join_url')
