"""create google oauth states table

Revision ID: f3a9c2b7d1e4
Revises: 0a1294ee8557
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c2b7d1e4'
down_revision: Union[str, Sequence[str], None] = '0a1294ee8557'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'google_oauth_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_google_oauth_states_id'), 'google_oauth_states', ['id'], unique=False)
    op.create_index(op.f('ix_google_oauth_states_state'), 'google_oauth_states', ['state'], unique=True)
    op.create_index(op.f('ix_google_oauth_states_user_id'), 'google_oauth_states', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_google_oauth_states_user_id'), table_name='google_oauth_states')
    op.drop_index(op.f('ix_google_oauth_states_state'), table_name='google_oauth_states')
    op.drop_index(op.f('ix_google_oauth_states_id'), table_name='google_oauth_states')
    op.drop_table('google_oauth_states')