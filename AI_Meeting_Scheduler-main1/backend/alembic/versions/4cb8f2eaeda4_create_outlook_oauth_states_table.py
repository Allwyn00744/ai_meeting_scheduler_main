"""create outlook oauth states table

Revision ID: 4cb8f2eaeda4
Revises: 0c4a1cca25ad
Create Date: 2026-07-16 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cb8f2eaeda4'
down_revision: Union[str, Sequence[str], None] = '0c4a1cca25ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'outlook_oauth_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_outlook_oauth_states_id'), 'outlook_oauth_states', ['id'], unique=False)
    op.create_index(op.f('ix_outlook_oauth_states_state'), 'outlook_oauth_states', ['state'], unique=True)
    op.create_index(op.f('ix_outlook_oauth_states_user_id'), 'outlook_oauth_states', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_outlook_oauth_states_user_id'), table_name='outlook_oauth_states')
    op.drop_index(op.f('ix_outlook_oauth_states_state'), table_name='outlook_oauth_states')
    op.drop_index(op.f('ix_outlook_oauth_states_id'), table_name='outlook_oauth_states')
    op.drop_table('outlook_oauth_states')
