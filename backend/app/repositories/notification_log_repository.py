from datetime import datetime

from sqlalchemy.orm import Session

from app.models.notification_log import NotificationLog


class NotificationLogRepository:
    """
    create() is written against an independent logging session
    supplied by each notification service (mirrors
    AnalyticsRepository.create_event / AnalyticsService
    .try_record_event) - it must never call session.commit() or
    session.rollback(). Commit/rollback/close of that session is
    owned exclusively by the caller.
    """

    @staticmethod
    def create(
        session: Session,
        user_id: int,
        channel: str,
        event_type: str,
        success: bool,
        meeting_id: int | None = None,
        error_detail: str | None = None,
    ) -> NotificationLog:
        row = NotificationLog(
            user_id=user_id,
            meeting_id=meeting_id,
            channel=channel,
            event_type=event_type,
            success=success,
            error_detail=error_detail[:2000] if error_detail else None,
        )

        session.add(row)
        session.flush()

        return row

    @staticmethod
    def get_between(
        db: Session,
        user_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> list[NotificationLog]:
        return (
            db.query(NotificationLog)
            .filter(
                NotificationLog.user_id == user_id,
                NotificationLog.created_at >= start_time,
                NotificationLog.created_at < end_time,
            )
            .all()
        )
