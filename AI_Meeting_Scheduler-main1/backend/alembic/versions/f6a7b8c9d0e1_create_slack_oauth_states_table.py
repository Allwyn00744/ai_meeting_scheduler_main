"""create slack oauth states table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-17 12:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('slack_oauth_states',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=255), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_slack_oauth_states_id'), 'slack_oauth_states', ['id'], unique=False)
    op.create_index(op.f('ix_slack_oauth_states_state'), 'slack_oauth_states', ['state'], unique=True)
    op.create_index(op.f('ix_slack_oauth_states_user_id'), 'slack_oauth_states', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_slack_oauth_states_user_id'), table_name='slack_oauth_states')
    op.drop_index(op.f('ix_slack_oauth_states_state'), table_name='slack_oauth_states')
    op.drop_index(op.f('ix_slack_oauth_states_id'), table_name='slack_oauth_states')
    op.drop_table('slack_oauth_states')
