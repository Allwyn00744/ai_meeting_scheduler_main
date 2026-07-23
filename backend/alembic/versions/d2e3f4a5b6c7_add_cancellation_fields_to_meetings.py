"""add cancellation fields to meetings

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-20 09:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'meetings',
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'meetings',
        sa.Column('cancelled_by_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_meetings_cancelled_by_id_users',
        'meetings',
        'users',
        ['cancelled_by_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_meetings_cancelled_by_id_users',
        'meetings',
        type_='foreignkey',
    )
    op.drop_column('meetings', 'cancelled_by_id')
    op.drop_column('meetings', 'cancelled_at')
