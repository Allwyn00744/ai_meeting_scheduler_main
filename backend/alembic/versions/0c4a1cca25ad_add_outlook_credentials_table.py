"""add outlook credentials table

Revision ID: 0c4a1cca25ad
Revises: d4e5f6a7b8c9
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c4a1cca25ad'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('outlook_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('access_token', sa.Text(), nullable=False),
    sa.Column('refresh_token', sa.Text(), nullable=True),
    sa.Column('scopes', sa.Text(), nullable=False),
    sa.Column('expiry', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outlook_credentials_id'), 'outlook_credentials', ['id'], unique=False)
    op.create_index(op.f('ix_outlook_credentials_user_id'), 'outlook_credentials', ['user_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_outlook_credentials_user_id'), table_name='outlook_credentials')
    op.drop_index(op.f('ix_outlook_credentials_id'), table_name='outlook_credentials')
    op.drop_table('outlook_credentials')
