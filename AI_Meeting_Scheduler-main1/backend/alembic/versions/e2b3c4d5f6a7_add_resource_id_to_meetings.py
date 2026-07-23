"""add resource_id to meetings

Revision ID: e2b3c4d5f6a7
Revises: d1a2b3c4e5f6
Create Date: 2026-07-09 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b3c4d5f6a7'
down_revision: Union[str, Sequence[str], None] = 'd1a2b3c4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'meetings',
        sa.Column('resource_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'meetings_resource_id_fkey',
        'meetings',
        'resources',
        ['resource_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'meetings_resource_id_fkey',
        'meetings',
        type_='foreignkey',
    )
    op.drop_column('meetings', 'resource_id')
