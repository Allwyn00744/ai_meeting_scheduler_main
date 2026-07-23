"""
NotificationLogService - best-effort write-only logging for
Notification Analytics V1, used by all four channel notification
services (email, Slack, WhatsApp, push).

Transaction isolation mirrors AnalyticsService.try_record_event
exactly: try_record never touches the caller's request-scoped
SQLAlchemy session. It opens its own independent Session from the
project's existing SessionLocal factory, commits or rolls back only
that independent session, always closes it, and never re-raises - a
logging failure must never affect the (already best-effort)
notification send itself, or the caller's own transaction state.
"""
import logging

from app.core.cache import analytics_prefix, cache_delete_prefix
from app.db.database import SessionLocal
from app.repositories.notification_log_repository import (
    NotificationLogRepository,
)

logger = logging.getLogger(__name__)


class NotificationLogService:

    @staticmethod
    def try_record(
        user_id: int,
        channel: str,
        event_type: str,
        success: bool,
        meeting_id: int | None = None,
        error_detail: str | None = None,
    ) -> None:
        log_db = SessionLocal()

        try:
            NotificationLogRepository.create(
                log_db,
                user_id=user_id,
                channel=channel,
                event_type=event_type,
                success=success,
                meeting_id=meeting_id,
                error_detail=error_detail,
            )
            log_db.commit()
            cache_delete_prefix(analytics_prefix(user_id))
        except Exception:
            log_db.rollback()
            logger.exception(
                "Failed to record notification log. "
                "channel=%s event_type=%s user_id=%s",
                channel,
                event_type,
                user_id,
            )
        finally:
            log_db.close()
