"""create zoom oauth states table

Revision ID: b5e8d3fa2c7e
Revises: a4f7c2e91b6d
Create Date: 2026-07-16 00:00:04.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5e8d3fa2c7e'
down_revision: Union[str, Sequence[str], None] = 'a4f7c2e91b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('zoom_oauth_states',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=255), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_zoom_oauth_states_id'), 'zoom_oauth_states', ['id'], unique=False)
    op.create_index(op.f('ix_zoom_oauth_states_state'), 'zoom_oauth_states', ['state'], unique=True)
    op.create_index(op.f('ix_zoom_oauth_states_user_id'), 'zoom_oauth_states', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_zoom_oauth_states_user_id'), table_name='zoom_oauth_states')
    op.drop_index(op.f('ix_zoom_oauth_states_state'), table_name='zoom_oauth_states')
    op.drop_index(op.f('ix_zoom_oauth_states_id'), table_name='zoom_oauth_states')
    op.drop_table('zoom_oauth_states')
