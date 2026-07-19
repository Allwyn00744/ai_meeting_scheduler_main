"""add cascade delete to meeting_participants fks

Revision ID: b6e2d4a9c3f1
Revises: f3a9c2b7d1e4
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e2d4a9c3f1'
down_revision: Union[str, Sequence[str], None] = 'f3a9c2b7d1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        'meeting_participants_meeting_id_fkey',
        'meeting_participants',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'meeting_participants_meeting_id_fkey',
        'meeting_participants',
        'meetings',
        ['meeting_id'],
        ['id'],
        ondelete='CASCADE',
    )

    op.drop_constraint(
        'meeting_participants_user_id_fkey',
        'meeting_participants',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'meeting_participants_user_id_fkey',
        'meeting_participants',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'meeting_participants_user_id_fkey',
        'meeting_participants',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'meeting_participants_user_id_fkey',
        'meeting_participants',
        'users',
        ['user_id'],
        ['id'],
    )

    op.drop_constraint(
        'meeting_participants_meeting_id_fkey',
        'meeting_participants',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'meeting_participants_meeting_id_fkey',
        'meeting_participants',
        'meetings',
        ['meeting_id'],
        ['id'],
    )
