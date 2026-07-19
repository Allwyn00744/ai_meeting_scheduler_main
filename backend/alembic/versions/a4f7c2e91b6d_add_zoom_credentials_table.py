"""add zoom credentials table

Revision ID: a4f7c2e91b6d
Revises: 5878d3150ab3
Create Date: 2026-07-16 00:00:03.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f7c2e91b6d'
down_revision: Union[str, Sequence[str], None] = '5878d3150ab3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('zoom_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('access_token', sa.Text(), nullable=False),
    sa.Column('refresh_token', sa.Text(), nullable=True),
    sa.Column('scopes', sa.Text(), nullable=False),
    sa.Column('expiry', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_zoom_credentials_id'), 'zoom_credentials', ['id'], unique=False)
    op.create_index(op.f('ix_zoom_credentials_user_id'), 'zoom_credentials', ['user_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_zoom_credentials_user_id'), table_name='zoom_credentials')
    op.drop_index(op.f('ix_zoom_credentials_id'), table_name='zoom_credentials')
    op.drop_table('zoom_credentials')
