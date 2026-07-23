from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analytics_event import AnalyticsEvent
from app.models.external_meeting_guest import ExternalMeetingGuest
from app.models.google_credential import GoogleCredential
from app.models.meeting import Meeting
from app.models.push_subscription import PushSubscription
from app.models.slack_credential import SlackCredential
from app.models.user import User

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

    Every other method here is read-only, written against the
    caller's normal request-scoped db session, and bounded to a single
    indexed query per method - callers that need per-day/week/month
    breakdowns or derived stats (median, percentiles, etc.) bucket the
    returned rows in Python rather than via DB-specific date functions,
    since tests run on SQLite and production runs on Postgres (see
    AnalyticsService for the range resolver and bucketing logic).
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

    # ---- Analytics Dashboard Extension ----------------------------------

    @staticmethod
    def get_meetings_in_range(
        db: Session,
        owner_id: int,
        start: datetime,
        end: datetime,
        include_cancelled: bool = False,
    ) -> list[Meeting]:
        """
        Every meeting owned by owner_id whose start_time falls in
        [start, end) - the single fetch that powers trend, duration,
        utilization, and productivity analytics. Anchored on
        start_time, matching the existing filter_by_date_range
        convention. include_cancelled=True is used only by
        cancellation analytics, which needs the cancelled rows
        themselves; every other caller wants the same
        "status != cancelled" exclusion the rest of the app already
        applies (see MeetingRepository).
        """
        query = db.query(Meeting).filter(
            Meeting.owner_id == owner_id,
            Meeting.start_time >= start,
            Meeting.start_time < end,
        )

        if not include_cancelled:
            query = query.filter(Meeting.status != "cancelled")

        return query.all()

    @staticmethod
    def get_cancelled_meetings_in_range(
        db: Session,
        owner_id: int,
        start: datetime,
        end: datetime,
    ) -> list[Meeting]:
        """
        Cancelled meetings, anchored on cancelled_at (not start_time) -
        cancellation trend/rate analytics is about when a meeting was
        cancelled, not when it was originally scheduled for.
        """
        return (
            db.query(Meeting)
            .filter(
                Meeting.owner_id == owner_id,
                Meeting.status == "cancelled",
                Meeting.cancelled_at.isnot(None),
                Meeting.cancelled_at >= start,
                Meeting.cancelled_at < end,
            )
            .all()
        )

    @staticmethod
    def get_resource_bookings_in_range(
        db: Session,
        owner_id: int,
        start: datetime,
        end: datetime,
    ) -> list[Meeting]:
        return (
            db.query(Meeting)
            .filter(
                Meeting.owner_id == owner_id,
                Meeting.status != "cancelled",
                Meeting.resource_id.isnot(None),
                Meeting.start_time >= start,
                Meeting.start_time < end,
            )
            .all()
        )

    @staticmethod
    def get_external_guest_count_by_meeting(
        db: Session,
        owner_id: int,
        start: datetime,
        end: datetime,
    ) -> dict[int, list[str]]:
        """
        {meeting_id: [guest_email, ...]} for every owned, non-cancelled
        meeting with at least one external guest in range - one join
        query rather than N+1 across meetings.
        """
        rows = (
            db.query(ExternalMeetingGuest.meeting_id, ExternalMeetingGuest.email)
            .join(Meeting, Meeting.id == ExternalMeetingGuest.meeting_id)
            .filter(
                Meeting.owner_id == owner_id,
                Meeting.status != "cancelled",
                Meeting.start_time >= start,
                Meeting.start_time < end,
            )
            .all()
        )

        result: dict[int, list[str]] = {}
        for meeting_id, email in rows:
            result.setdefault(meeting_id, []).append(email)

        return result

    # ---- Integration Analytics (per-user counts) ------------------------

    @staticmethod
    def count_synced_meetings_in_range(
        db: Session,
        owner_id: int,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        base = db.query(Meeting).filter(
            Meeting.owner_id == owner_id,
            Meeting.status != "cancelled",
            Meeting.start_time >= start,
            Meeting.start_time < end,
        )

        return {
            "google": base.filter(Meeting.google_event_id.isnot(None)).count(),
            "outlook": base.filter(Meeting.outlook_event_id.isnot(None)).count(),
            "zoom": base.filter(Meeting.zoom_meeting_id.isnot(None)).count(),
            "teams": base.filter(Meeting.teams_join_url.isnot(None)).count(),
        }

    # ---- Team Analytics V1: the only cross-user queries in the app -----
    # Aggregate-only (COUNT ... GROUP BY), never returns per-user rows -
    # see AnalyticsService.get_team_overview.

    @staticmethod
    def get_department_distribution(db: Session) -> list[tuple[str, int]]:
        return (
            db.query(User.department, func.count(User.id))
            .filter(User.department.isnot(None), User.department != "")
            .group_by(User.department)
            .order_by(func.count(User.id).desc())
            .all()
        )

    @staticmethod
    def get_timezone_distribution(db: Session) -> list[tuple[str, int]]:
        return (
            db.query(User.timezone, func.count(User.id))
            .group_by(User.timezone)
            .order_by(func.count(User.id).desc())
            .all()
        )

    @staticmethod
    def get_meeting_count_by_department_in_range(
        db: Session,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        rows = (
            db.query(User.department, func.count(Meeting.id))
            .join(Meeting, Meeting.owner_id == User.id)
            .filter(
                User.department.isnot(None),
                User.department != "",
                Meeting.status != "cancelled",
                Meeting.start_time >= start,
                Meeting.start_time < end,
            )
            .group_by(User.department)
            .all()
        )

        return {department: count for department, count in rows}

    @staticmethod
    def count_total_users(db: Session) -> int:
        return db.query(User).count()

    @staticmethod
    def count_users_with_department(db: Session) -> int:
        return (
            db.query(User)
            .filter(User.department.isnot(None), User.department != "")
            .count()
        )

    @staticmethod
    def count_connected_users_by_integration(db: Session) -> dict[str, int]:
        return {
            "google": db.query(GoogleCredential).count(),
            "slack": db.query(SlackCredential).count(),
            "push": (
                db.query(PushSubscription.user_id)
                .distinct()
                .count()
            ),
        }
