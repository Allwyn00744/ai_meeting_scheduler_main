"""add slack credentials table

Revision ID: e5f6a7b8c9d0
Revises: d00d72ef899c
Create Date: 2026-07-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd00d72ef899c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('slack_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('access_token', sa.Text(), nullable=False),
    sa.Column('team_id', sa.String(length=255), nullable=False),
    sa.Column('team_name', sa.String(length=255), nullable=True),
    sa.Column('slack_user_id', sa.String(length=255), nullable=False),
    sa.Column('scopes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_slack_credentials_id'), 'slack_credentials', ['id'], unique=False)
    op.create_index(op.f('ix_slack_credentials_user_id'), 'slack_credentials', ['user_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_slack_credentials_user_id'), table_name='slack_credentials')
    op.drop_index(op.f('ix_slack_credentials_id'), table_name='slack_credentials')
    op.drop_table('slack_credentials')
