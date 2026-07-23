"""create meeting owner followup emails table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'meeting_owner_followup_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('meeting_note_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['meeting_note_id'],
            ['meeting_owner_notes.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'meeting_note_id',
            name='uq_meeting_owner_followup_emails_meeting_note_id',
        ),
    )
    op.create_index(
        op.f('ix_meeting_owner_followup_emails_id'),
        'meeting_owner_followup_emails',
        ['id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_meeting_owner_followup_emails_id'),
        table_name='meeting_owner_followup_emails',
    )
    op.drop_table('meeting_owner_followup_emails')
