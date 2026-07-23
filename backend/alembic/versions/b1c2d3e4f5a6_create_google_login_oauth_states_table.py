"""create google login oauth states table

Revision ID: b1c2d3e4f5a6
Revises: f4a5b6c7d8e9
Create Date: 2026-07-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'google_login_oauth_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_google_login_oauth_states_id'),
        'google_login_oauth_states',
        ['id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_google_login_oauth_states_state'),
        'google_login_oauth_states',
        ['state'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_google_login_oauth_states_state'),
        table_name='google_login_oauth_states',
    )
    op.drop_index(
        op.f('ix_google_login_oauth_states_id'),
        table_name='google_login_oauth_states',
    )
    op.drop_table('google_login_oauth_states')
