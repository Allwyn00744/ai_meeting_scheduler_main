"""
AnalyticsService - KPI aggregation (read) and best-effort conflict-event
recording (write).

Transaction isolation: try_record_event never touches the caller's
request-scoped SQLAlchemy session. It opens its own independent Session
from the project's existing SessionLocal factory (app.db.database),
commits or rolls back only that independent session, always closes it,
and never re-raises - a failure here must never change the HTTP
response of the core scheduling/creation flow that called it, and must
never leave the caller's own session in a broken state.
"""
import logging

from sqlalchemy.orm import Session

from app.core.cache import (
    KPI_TTL_SECONDS,
    cache_delete,
    cache_get,
    cache_set,
    kpis_key,
)
from app.db.database import SessionLocal
from app.repositories.analytics_repository import AnalyticsRepository

logger = logging.getLogger(__name__)

# Fixed, documented V1 constants. meetings_scheduled and
# conflicts_avoided are both live counts of already-deduplicated
# persisted rows, so this formula cannot itself drift or double count.
MINUTES_PER_MEETING_SCHEDULED = 5
MINUTES_PER_CONFLICT_AVOIDED = 10

# Event type constants - the single allowlist, mirrored by the
# ck_analytics_events_event_type CHECK constraint on the model.
EVENT_CONFLICT_BLOCKED_OWNER = "CONFLICT_BLOCKED_OWNER"
EVENT_CONFLICT_BLOCKED_PARTICIPANT = "CONFLICT_BLOCKED_PARTICIPANT"
EVENT_CONFLICT_BLOCKED_RESOURCE = "CONFLICT_BLOCKED_RESOURCE"


class AnalyticsService:

    @staticmethod
    def try_record_event(
        user_id: int,
        event_type: str,
        meeting_id: int | None = None,
    ) -> None:
        """
        Best-effort conflict-event recording on a fully independent
        session. Never raises. Does not accept the caller's db session
        - it is intentionally self-contained so it cannot commit,
        rollback, expire, or otherwise alter the caller's transaction
        state.
        """
        analytics_db: Session = SessionLocal()

        try:
            AnalyticsRepository.create_event(
                analytics_db,
                user_id,
                event_type,
                meeting_id,
            )
            analytics_db.commit()
            cache_delete(kpis_key(user_id))
        except Exception:
            analytics_db.rollback()
            logger.exception(
                "Failed to record analytics event. "
                "event_type=%s user_id=%s",
                event_type,
                user_id,
            )
        finally:
            analytics_db.close()

    @staticmethod
    def get_kpis(db: Session, current_user):
        cache_key = kpis_key(current_user.id)
        cached = cache_get(cache_key)

        if cached is not None:
            return cached

        meetings_scheduled = (
            AnalyticsRepository.count_meetings_scheduled(
                db,
                current_user.id,
            )
        )

        conflicts_avoided = (
            AnalyticsRepository.count_conflicts_avoided(
                db,
                current_user.id,
            )
        )

        time_saved_minutes = (
            meetings_scheduled * MINUTES_PER_MEETING_SCHEDULED
            + conflicts_avoided * MINUTES_PER_CONFLICT_AVOIDED
        )

        result = {
            "meetings_scheduled": meetings_scheduled,
            "conflicts_avoided": conflicts_avoided,
            "time_saved_minutes": time_saved_minutes,
        }

        cache_set(cache_key, result, KPI_TTL_SECONDS)

        return result
