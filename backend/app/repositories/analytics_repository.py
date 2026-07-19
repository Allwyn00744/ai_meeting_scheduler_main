from sqlalchemy.orm import Session

from app.models.analytics_event import AnalyticsEvent
from app.models.meeting import Meeting

CONFLICT_EVENT_TYPES = (
    "CONFLICT_BLOCKED_OWNER",
    "CONFLICT_BLOCKED_PARTICIPANT",
    "CONFLICT_BLOCKED_RESOURCE",
)


class AnalyticsRepository:
    """
    create_event is written against an independent analytics session
    supplied by AnalyticsService.try_record_event - it must never call
    session.commit() or session.rollback(). Commit/rollback/close of
    that session is owned exclusively by the service.

    The count_* methods are read-only and are written against the
    caller's normal request-scoped db session.
    """

    @staticmethod
    def create_event(
        session: Session,
        user_id: int,
        event_type: str,
        meeting_id: int | None = None,
    ):
        event = AnalyticsEvent(
            user_id=user_id,
            event_type=event_type,
            meeting_id=meeting_id,
        )

        session.add(event)
        session.flush()

        return event

    @staticmethod
    def count_meetings_scheduled(
        db: Session,
        user_id: int,
    ) -> int:
        return (
            db.query(Meeting)
            .filter(Meeting.owner_id == user_id)
            .count()
        )

    @staticmethod
    def count_conflicts_avoided(
        db: Session,
        user_id: int,
    ) -> int:
        return (
            db.query(AnalyticsEvent)
            .filter(
                AnalyticsEvent.user_id == user_id,
                AnalyticsEvent.event_type.in_(CONFLICT_EVENT_TYPES),
            )
            .count()
        )
