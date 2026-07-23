"""add indexes on meetings hot-path filter columns

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-20 12:00:00.000000

Production QA pass: owner_id, start_time, end_time, status, and
resource_id are all filtered/joined on by every conflict check,
meeting listing, and the background "mark completed" job (see
MeetingRepository.get_user_meetings, get_resource_bookings_between,
filter_by_status, get_all) but had no index - every one of those
queries was doing a full table scan. series_id already has
ix_meetings_series_id from the previous migration, so it's not
repeated here.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_meetings_owner_id', 'meetings', ['owner_id'], unique=False)
    op.create_index('ix_meetings_start_time', 'meetings', ['start_time'], unique=False)
    op.create_index('ix_meetings_end_time', 'meetings', ['end_time'], unique=False)
    op.create_index('ix_meetings_status', 'meetings', ['status'], unique=False)
    op.create_index('ix_meetings_resource_id', 'meetings', ['resource_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_meetings_resource_id', table_name='meetings')
    op.drop_index('ix_meetings_status', table_name='meetings')
    op.drop_index('ix_meetings_end_time', table_name='meetings')
    op.drop_index('ix_meetings_start_time', table_name='meetings')
    op.drop_index('ix_meetings_owner_id', table_name='meetings')
