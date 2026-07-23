"""
AnalyticsService - KPI aggregation (read) and best-effort conflict-event
recording (write), plus the Analytics Dashboard Extension: date-range
resolution and every /analytics/* aggregation beyond /kpis.

Transaction isolation: try_record_event never touches the caller's
request-scoped SQLAlchemy session. It opens its own independent Session
from the project's existing SessionLocal factory (app.db.database),
commits or rolls back only that independent session, always closes it,
and never re-raises - a failure here must never change the HTTP
response of the core scheduling/creation flow that called it, and must
never leave the caller's own session in a broken state.

Every number below is derived from real, already-persisted data. Where
the underlying data simply doesn't exist yet for a given user/range
(no meetings, no availability rows, nobody has set a department), the
result is 0/empty rather than an invented placeholder - see individual
methods for the exact "no data" behavior.
"""
import calendar
import logging
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import (
    ANALYTICS_TTL_SECONDS,
    KPI_TTL_SECONDS,
    analytics_key,
    cache_delete,
    cache_get,
    cache_set,
    kpis_key,
)
from app.db.database import SessionLocal
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.meeting_reschedule_history_repository import (
    MeetingRescheduleHistoryRepository,
)
from app.repositories.notification_log_repository import (
    NotificationLogRepository,
)
from app.repositories.resource_repository import ResourceRepository
from app.schemas.analytics import ResolvedRange

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

VALID_RANGE_KEYS = (
    "today", "7d", "30d", "90d", "this_month", "last_month", "custom",
)

WEEKDAY_NAMES = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)

# A gap between meetings shorter than this is "back-to-back" for the
# insight generator below.
BACK_TO_BACK_GAP_MINUTES = 15
# A free gap at least this long counts as a "deep work" block.
DEEP_WORK_MIN_MINUTES = 60


def _user_zoneinfo(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("UTC")


def _bucket_key(moment: datetime, granularity: str) -> str:
    if granularity == "day":
        return moment.date().isoformat()
    if granularity == "week":
        iso = moment.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if granularity == "month":
        return f"{moment.year}-{moment.month:02d}"
    raise ValueError(f"Unknown granularity: {granularity}")


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

    # ---- Analytics Dashboard Extension: date-range resolution ----------

    @staticmethod
    def resolve_date_range(
        range_key: str,
        start: date | None,
        end: date | None,
        user_timezone: str,
    ) -> ResolvedRange:
        """
        Resolves the range/start/end query params every /analytics/*
        endpoint (besides /kpis) accepts into a concrete UTC
        [start, end) window, evaluated relative to "now" in the user's
        own timezone so "Today"/"This Month" etc. line up with their
        actual calendar day/month rather than UTC's.
        """
        if range_key not in VALID_RANGE_KEYS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unknown range '{range_key}'. Expected one of: "
                    f"{', '.join(VALID_RANGE_KEYS)}."
                ),
            )

        tz = _user_zoneinfo_by_name(user_timezone)
        now_local = datetime.now(tz)
        today_start = now_local.replace(
            hour=0, minute=0, second=0, microsecond=0,
        )

        if range_key == "today":
            range_start = today_start
            range_end = today_start + timedelta(days=1)
        elif range_key == "7d":
            range_start = today_start - timedelta(days=6)
            range_end = today_start + timedelta(days=1)
        elif range_key == "30d":
            range_start = today_start - timedelta(days=29)
            range_end = today_start + timedelta(days=1)
        elif range_key == "90d":
            range_start = today_start - timedelta(days=89)
            range_end = today_start + timedelta(days=1)
        elif range_key == "this_month":
            range_start = today_start.replace(day=1)
            last_day = calendar.monthrange(
                range_start.year, range_start.month,
            )[1]
            range_end = range_start.replace(day=last_day) + timedelta(days=1)
        elif range_key == "last_month":
            first_of_this_month = today_start.replace(day=1)
            range_end = first_of_this_month
            range_start = (
                first_of_this_month - timedelta(days=1)
            ).replace(day=1)
        else:  # custom
            if start is None or end is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "start and end (YYYY-MM-DD) are required "
                        "when range=custom."
                    ),
                )
            range_start = datetime(
                start.year, start.month, start.day, tzinfo=tz,
            )
            range_end = datetime(
                end.year, end.month, end.day, tzinfo=tz,
            ) + timedelta(days=1)
            if range_end <= range_start:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="end must be on or after start.",
                )

        return ResolvedRange(
            start=range_start.astimezone(dt_timezone.utc),
            end=range_end.astimezone(dt_timezone.utc),
        )

    # ---- Overview: trend, duration, utilization, productivity ----------

    @staticmethod
    def get_overview(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        cache_key = analytics_key(
            current_user.id, "overview",
            resolved_range.start.isoformat(), resolved_range.end.isoformat(),
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        start, end = resolved_range.start, resolved_range.end
        meetings = AnalyticsRepository.get_meetings_in_range(
            db, current_user.id, start, end,
        )
        cancelled = AnalyticsRepository.get_cancelled_meetings_in_range(
            db, current_user.id, start, end,
        )
        reschedules = MeetingRescheduleHistoryRepository.get_between(
            db, current_user.id, start, end,
        )

        trend_daily = AnalyticsService._build_trend(
            meetings, cancelled, reschedules, "day",
        )
        trend_weekly = AnalyticsService._build_trend(
            meetings, cancelled, reschedules, "week",
        )
        trend_monthly = AnalyticsService._build_trend(
            meetings, cancelled, reschedules, "month",
        )

        duration = AnalyticsService._duration_stats(meetings, start, end)

        tz = _user_zoneinfo(current_user)
        availability_rows = AvailabilityRepository.get_by_user(
            db, current_user.id,
        )
        available_minutes, focus_minutes, deep_work_minutes = (
            AnalyticsService._compute_time_budget(
                meetings, availability_rows, start, end, tz,
            )
        )
        booked_minutes = sum(
            (m.end_time - m.start_time).total_seconds() / 60
            for m in meetings
        )

        utilization_pct = (
            round(min(100, (booked_minutes / available_minutes) * 100), 1)
            if available_minutes > 0 else 0.0
        )
        free_pct = round(max(0.0, 100.0 - utilization_pct), 1)

        days_in_range = max(1, (end - start).days)
        total_in_window = len(meetings) + len(cancelled)
        productivity_score = (
            round(100 * len(meetings) / total_in_window)
            if total_in_window > 0 else 0
        )

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "trend_daily": trend_daily,
            "trend_weekly": trend_weekly,
            "trend_monthly": trend_monthly,
            "duration": duration,
            "utilization": {
                "booked_hours": round(booked_minutes / 60, 1),
                "available_hours": round(available_minutes / 60, 1),
                "utilization_pct": utilization_pct,
                "free_pct": free_pct,
            },
            "productivity": {
                "meeting_time_minutes": round(booked_minutes),
                "focus_time_minutes": round(focus_minutes),
                "deep_work_minutes": round(deep_work_minutes),
                "average_meetings_per_day": round(
                    len(meetings) / days_in_range, 2,
                ),
                "productivity_score": productivity_score,
                "meeting_load_score": round(utilization_pct),
            },
        }

        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    @staticmethod
    def _build_trend(
        meetings: list[Meeting],
        cancelled: list[Meeting],
        reschedules: list,
        granularity: str,
    ) -> list[dict]:
        now = datetime.now(dt_timezone.utc)
        buckets: dict[str, dict[str, int]] = defaultdict(
            lambda: {"upcoming": 0, "completed": 0, "cancelled": 0, "rescheduled": 0}
        )

        for meeting in meetings:
            key = _bucket_key(meeting.start_time, granularity)
            if meeting.end_time < now:
                buckets[key]["completed"] += 1
            else:
                buckets[key]["upcoming"] += 1

        for meeting in cancelled:
            key = _bucket_key(meeting.cancelled_at, granularity)
            buckets[key]["cancelled"] += 1

        for row in reschedules:
            key = _bucket_key(row.created_at, granularity)
            buckets[key]["rescheduled"] += 1

        return [
            {"date": key, **counts}
            for key, counts in sorted(buckets.items())
        ]

    @staticmethod
    def _duration_stats(
        meetings: list[Meeting],
        start: datetime,
        end: datetime,
    ) -> dict:
        if not meetings:
            return {
                "average_minutes": 0.0,
                "median_minutes": 0.0,
                "longest_minutes": 0,
                "shortest_minutes": 0,
                "total_hours": 0.0,
                "average_daily_minutes": 0.0,
            }

        durations = [
            (m.end_time - m.start_time).total_seconds() / 60
            for m in meetings
        ]
        days_in_range = max(1, (end - start).days)

        return {
            "average_minutes": round(statistics.mean(durations), 1),
            "median_minutes": round(statistics.median(durations), 1),
            "longest_minutes": round(max(durations)),
            "shortest_minutes": round(min(durations)),
            "total_hours": round(sum(durations) / 60, 1),
            "average_daily_minutes": round(sum(durations) / days_in_range, 1),
        }

    @staticmethod
    def _availability_window_for_date(
        availability_rows: list,
        the_date: date,
        tz: ZoneInfo,
    ) -> tuple[datetime, datetime] | None:
        """
        The user's declared Availability window for this calendar date
        (see Availability model: one row per day-of-week), converted
        to a concrete UTC [start, end) interval for that specific
        date. None if the user has no available window on that
        weekday - "no data" rather than an assumed 24/7 or 9-5 default.
        """
        weekday_name = the_date.strftime("%A")
        row = next(
            (
                r for r in availability_rows
                if r.day_of_week == weekday_name and r.is_available
            ),
            None,
        )
        if row is None:
            return None

        local_start = datetime.combine(the_date, row.start_time, tzinfo=tz)
        local_end = datetime.combine(the_date, row.end_time, tzinfo=tz)
        return local_start.astimezone(dt_timezone.utc), local_end.astimezone(dt_timezone.utc)

    @staticmethod
    def _compute_time_budget(
        meetings: list[Meeting],
        availability_rows: list,
        start: datetime,
        end: datetime,
        tz: ZoneInfo,
    ) -> tuple[float, float, float]:
        """
        Walks every calendar date in [start, end), and for each one
        that has a declared Availability window, subtracts that day's
        meetings from it to get free intervals. Returns
        (available_minutes, focus_minutes, deep_work_minutes) - all
        real, derived from the user's own Availability + Meeting rows.
        A user with no Availability rows at all gets 0 for every
        figure here (not a fabricated default window).
        """
        available_minutes = 0.0
        focus_minutes = 0.0
        deep_work_minutes = 0.0

        current_date = start.astimezone(tz).date()
        end_date = end.astimezone(tz).date()

        while current_date < end_date:
            window = AnalyticsService._availability_window_for_date(
                availability_rows, current_date, tz,
            )
            if window is not None:
                window_start, window_end = window
                available_minutes += (
                    window_end - window_start
                ).total_seconds() / 60

                busy = sorted(
                    (
                        (max(m.start_time, window_start), min(m.end_time, window_end))
                        for m in meetings
                        if m.start_time < window_end and m.end_time > window_start
                    ),
                    key=lambda pair: pair[0],
                )

                cursor = window_start
                for busy_start, busy_end in busy:
                    if busy_start > cursor:
                        gap_minutes = (busy_start - cursor).total_seconds() / 60
                        focus_minutes += gap_minutes
                        if gap_minutes >= DEEP_WORK_MIN_MINUTES:
                            deep_work_minutes += gap_minutes
                    cursor = max(cursor, busy_end)

                if cursor < window_end:
                    gap_minutes = (window_end - cursor).total_seconds() / 60
                    focus_minutes += gap_minutes
                    if gap_minutes >= DEEP_WORK_MIN_MINUTES:
                        deep_work_minutes += gap_minutes

            current_date += timedelta(days=1)

        return available_minutes, focus_minutes, deep_work_minutes

    # ---- Reschedule Analytics -------------------------------------------

    @staticmethod
    def get_reschedule_analytics(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        cache_key = analytics_key(
            current_user.id, "reschedule",
            resolved_range.start.isoformat(), resolved_range.end.isoformat(),
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        start, end = resolved_range.start, resolved_range.end
        reschedules = MeetingRescheduleHistoryRepository.get_between(
            db, current_user.id, start, end,
        )
        meetings = AnalyticsRepository.get_meetings_in_range(
            db, current_user.id, start, end,
        )

        total_rescheduled = len(reschedules)
        # Share of this window's scheduling activity that involved a
        # reschedule - denominator is meetings currently scheduled to
        # start in-range plus the reschedule events themselves, since
        # a rescheduled meeting's new start_time may fall outside the
        # window it was rescheduled within.
        denominator = len(meetings) + total_rescheduled
        reschedule_rate_pct = (
            round(100 * total_rescheduled / denominator, 1)
            if denominator > 0 else 0.0
        )

        busiest_day = None
        time_slot = None
        if reschedules:
            tz = _user_zoneinfo(current_user)
            day_counts = Counter(
                row.created_at.astimezone(tz).strftime("%A")
                for row in reschedules
            )
            busiest_day = day_counts.most_common(1)[0][0]

            slot_counts = Counter(
                _hour_slot_label(row.new_start_time.astimezone(tz))
                for row in reschedules
            )
            time_slot = slot_counts.most_common(1)[0][0]

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "total_rescheduled": total_rescheduled,
            "reschedule_rate_pct": reschedule_rate_pct,
            "busiest_reschedule_day": busiest_day,
            "most_common_time_slot": time_slot,
        }
        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    # ---- Cancellation Analytics ------------------------------------------

    @staticmethod
    def get_cancellation_analytics(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        cache_key = analytics_key(
            current_user.id, "cancellations",
            resolved_range.start.isoformat(), resolved_range.end.isoformat(),
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        start, end = resolved_range.start, resolved_range.end
        cancelled = AnalyticsRepository.get_cancelled_meetings_in_range(
            db, current_user.id, start, end,
        )
        meetings = AnalyticsRepository.get_meetings_in_range(
            db, current_user.id, start, end,
        )

        total_in_window = len(meetings) + len(cancelled)
        cancellation_rate_pct = (
            round(100 * len(cancelled) / total_in_window, 1)
            if total_in_window > 0 else 0.0
        )

        # Only the meeting owner can ever cancel a meeting today (see
        # MeetingService.delete_meeting's 403 for anyone else) - so
        # this split will always read 100/0 until a participant-cancel
        # capability exists. Computed honestly rather than hardcoded,
        # so it stays correct if that ever changes.
        cancelled_by_organizer = sum(
            1 for m in cancelled if m.cancelled_by_id == m.owner_id
        )
        cancelled_by_participant = len(cancelled) - cancelled_by_organizer

        trend = defaultdict(int)
        for m in cancelled:
            trend[m.cancelled_at.date().isoformat()] += 1

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "cancellation_rate_pct": cancellation_rate_pct,
            "cancelled_count": len(cancelled),
            "cancelled_by_organizer_count": cancelled_by_organizer,
            "cancelled_by_participant_count": cancelled_by_participant,
            "trend_daily": [
                {"date": d, "count": c} for d, c in sorted(trend.items())
            ],
        }
        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    # ---- Notification Analytics ------------------------------------------

    @staticmethod
    def get_notification_analytics(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        cache_key = analytics_key(
            current_user.id, "notifications",
            resolved_range.start.isoformat(), resolved_range.end.isoformat(),
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        rows = NotificationLogRepository.get_between(
            db, current_user.id, resolved_range.start, resolved_range.end,
        )

        by_channel: dict[str, dict] = {}
        for channel in ("email", "slack", "whatsapp", "push"):
            channel_rows = [r for r in rows if r.channel == channel]
            sent = sum(1 for r in channel_rows if r.success)
            failed = sum(1 for r in channel_rows if not r.success)
            total = sent + failed
            by_channel[channel] = {
                "sent": sent,
                "failed": failed,
                "success_pct": round(100 * sent / total, 1) if total > 0 else 0.0,
            }

        total_sent = sum(c["sent"] for c in by_channel.values())
        total_attempts = len(rows)
        overall_success_pct = (
            round(100 * total_sent / total_attempts, 1)
            if total_attempts > 0 else 0.0
        )

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "by_channel": by_channel,
            "overall_success_pct": overall_success_pct,
        }
        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    # ---- Integration Analytics --------------------------------------------

    @staticmethod
    def get_integration_analytics(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        cache_key = analytics_key(
            current_user.id, "integrations",
            resolved_range.start.isoformat(), resolved_range.end.isoformat(),
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        synced = AnalyticsRepository.count_synced_meetings_in_range(
            db, current_user.id, resolved_range.start, resolved_range.end,
        )
        # The only cross-user numbers in this endpoint: aggregate
        # connected-user counts, not tied to any individual identity -
        # matches the same minimal Team Analytics scope used by
        # get_team_overview below.
        connected_users = AnalyticsRepository.count_connected_users_by_integration(db)
        total_users = AnalyticsRepository.count_total_users(db)

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "google_synced_count": synced["google"],
            "outlook_synced_count": synced["outlook"],
            "zoom_meetings_count": synced["zoom"],
            "teams_meetings_count": synced["teams"],
            "connected_users": connected_users,
            "total_users": total_users,
        }
        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    # ---- Resource Analytics ------------------------------------------------

    @staticmethod
    def get_resource_analytics(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        cache_key = analytics_key(
            current_user.id, "resources",
            resolved_range.start.isoformat(), resolved_range.end.isoformat(),
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        start, end = resolved_range.start, resolved_range.end
        bookings = AnalyticsRepository.get_resource_bookings_in_range(
            db, current_user.id, start, end,
        )
        meetings = AnalyticsRepository.get_meetings_in_range(
            db, current_user.id, start, end,
        )

        range_hours = max(0.0, (end - start).total_seconds() / 3600)

        by_resource: dict[int, list[Meeting]] = defaultdict(list)
        for m in bookings:
            by_resource[m.resource_id].append(m)

        resources = ResourceRepository.get_by_ids(db, list(by_resource.keys()))

        usages = []
        for resource_id, resource_meetings in by_resource.items():
            resource = resources.get(resource_id)
            if resource is None:
                continue
            booked_hours = sum(
                (m.end_time - m.start_time).total_seconds() / 3600
                for m in resource_meetings
            )
            usages.append({
                "resource_id": resource_id,
                "name": resource.name,
                "booking_count": len(resource_meetings),
                "booked_hours": round(booked_hours, 1),
                "utilization_pct": (
                    round(min(100, (booked_hours / range_hours) * 100), 1)
                    if range_hours > 0 else 0.0
                ),
            })

        usages.sort(key=lambda u: u["booking_count"], reverse=True)
        most_used = usages[0] if usages else None
        least_used = usages[-1] if len(usages) > 1 else (usages[0] if usages else None)
        average_utilization_pct = (
            round(sum(u["utilization_pct"] for u in usages) / len(usages), 1)
            if usages else 0.0
        )

        virtual_count = 0
        physical_count = 0
        for m in meetings:
            is_virtual = bool(m.zoom_join_url or m.teams_join_url or m.google_meet_link)
            if is_virtual:
                virtual_count += 1
            elif m.resource_id is not None or m.location:
                physical_count += 1

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "most_used": most_used,
            "least_used": least_used,
            "average_utilization_pct": average_utilization_pct,
            "virtual_meeting_count": virtual_count,
            "physical_meeting_count": physical_count,
        }
        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    # ---- External Guest Analytics ------------------------------------------

    @staticmethod
    def get_guest_analytics(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        cache_key = analytics_key(
            current_user.id, "guests",
            resolved_range.start.isoformat(), resolved_range.end.isoformat(),
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        start, end = resolved_range.start, resolved_range.end
        meetings = AnalyticsRepository.get_meetings_in_range(
            db, current_user.id, start, end,
        )
        guest_map = AnalyticsRepository.get_external_guest_count_by_meeting(
            db, current_user.id, start, end,
        )

        external_meeting_count = len(guest_map)
        internal_meeting_count = len(meetings) - external_meeting_count

        domain_counts: Counter[str] = Counter()
        for emails in guest_map.values():
            for email in emails:
                domain = email.rsplit("@", 1)[-1].lower() if "@" in email else email
                domain_counts[domain] += 1

        top_domains = [
            {"domain": domain, "count": count}
            for domain, count in domain_counts.most_common(10)
        ]

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "internal_meeting_count": max(0, internal_meeting_count),
            "external_meeting_count": external_meeting_count,
            # No separate "company name" field exists anywhere in this
            # schema - the guest's email domain is the closest real
            # proxy, so top_companies intentionally mirrors
            # guest_domains rather than inventing company names.
            "guest_domains": top_domains,
            "top_companies": top_domains[:5],
        }
        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    # ---- Team Analytics V1 (minimal, aggregate-only, cross-user) --------

    @staticmethod
    def get_team_overview(
        db: Session,
        resolved_range: ResolvedRange,
    ) -> dict:
        """
        The only endpoint (besides the connected-user counts folded
        into get_integration_analytics) that reads across every user
        rather than scoping to current_user - by design, per the
        approved minimal Team Analytics scope: aggregate counts only
        (department/timezone distribution), never a per-user
        breakdown, so no individual's meeting activity is exposed to
        anyone else.
        """
        cache_key = f"team-overview:{resolved_range.start.isoformat()}:{resolved_range.end.isoformat()}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        dept_user_counts = dict(
            AnalyticsRepository.get_department_distribution(db)
        )
        dept_meeting_counts = (
            AnalyticsRepository.get_meeting_count_by_department_in_range(
                db, resolved_range.start, resolved_range.end,
            )
        )
        tz_counts = AnalyticsRepository.get_timezone_distribution(db)

        by_department = [
            {
                "department": department,
                "user_count": user_count,
                "meeting_count": dept_meeting_counts.get(department, 0),
            }
            for department, user_count in dept_user_counts.items()
        ]
        by_department.sort(key=lambda d: d["meeting_count"], reverse=True)

        result = {
            "range": resolved_range.model_dump(mode="json"),
            "by_department": by_department,
            "by_timezone": [
                {"timezone": tz_name, "user_count": count}
                for tz_name, count in tz_counts
            ],
            "total_users": AnalyticsRepository.count_total_users(db),
            "users_with_department_set": (
                AnalyticsRepository.count_users_with_department(db)
            ),
        }
        cache_set(cache_key, result, ANALYTICS_TTL_SECONDS)
        return result

    # ---- AI Insights: rule-based, generated from real aggregates -------

    @staticmethod
    def get_insights(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> dict:
        """
        Every insight below is a template that only renders when its
        underlying statistical condition is actually met by this
        user's real data in this range, with every number interpolated
        from the same aggregates the other /analytics/* endpoints
        compute - nothing here is a canned/random message. No LLM call
        (this stays fast and has no external dependency); see the
        Analytics Dashboard Extension plan for why.
        """
        overview = AnalyticsService.get_overview(db, current_user, resolved_range)
        cancellations = AnalyticsService.get_cancellation_analytics(
            db, current_user, resolved_range,
        )

        insights: list[dict] = []

        booked = overview["productivity"]["meeting_time_minutes"]
        available = overview["utilization"]["booked_hours"] * 60 + overview["productivity"]["focus_time_minutes"]
        if available > 0:
            workday_pct = round(100 * booked / available)
            if workday_pct >= 30:
                insights.append({
                    "id": "workday-meeting-share",
                    "message": f"You spend {workday_pct}% of your available time in meetings.",
                    "tone": "warning" if workday_pct >= 60 else "info",
                })

        daily_counts: Counter[str] = Counter()
        for point in overview["trend_daily"]:
            weekday = datetime.fromisoformat(point["date"]).strftime("%A")
            daily_counts[weekday] += point["upcoming"] + point["completed"]
        if daily_counts:
            busiest_day, busiest_count = daily_counts.most_common(1)[0]
            if busiest_count > 0:
                insights.append({
                    "id": "busiest-day",
                    "message": f"{busiest_day} is your busiest day, with {busiest_count} meeting(s) in this range.",
                    "tone": "info",
                })

        back_to_back = AnalyticsService._count_back_to_back(
            AnalyticsRepository.get_meetings_in_range(
                db, current_user.id, resolved_range.start, resolved_range.end,
            )
        )
        if back_to_back >= 3:
            insights.append({
                "id": "back-to-back",
                "message": f"You have {back_to_back} back-to-back meetings (less than {BACK_TO_BACK_GAP_MINUTES} minutes apart) in this range.",
                "tone": "warning",
            })

        weekly = overview["trend_weekly"]
        if len(weekly) >= 2:
            last_two = weekly[-2:]
            prev_total = last_two[0]["upcoming"] + last_two[0]["completed"]
            curr_total = last_two[1]["upcoming"] + last_two[1]["completed"]
            if prev_total > 0:
                change_pct = round(100 * (curr_total - prev_total) / prev_total)
                if abs(change_pct) >= 15:
                    direction = "increased" if change_pct > 0 else "decreased"
                    insights.append({
                        "id": "week-over-week-load",
                        "message": f"Your meeting load {direction} {abs(change_pct)}% week over week.",
                        "tone": "warning" if change_pct > 0 else "positive",
                    })

        if cancellations["cancelled_count"] > 0 and cancellations["trend_daily"]:
            tz = _user_zoneinfo(current_user)
            day_counts: Counter[str] = Counter()
            for point in cancellations["trend_daily"]:
                weekday = date.fromisoformat(point["date"]).strftime("%A")
                day_counts[weekday] += point["count"]
            worst_day, worst_count = day_counts.most_common(1)[0]
            insights.append({
                "id": "cancellation-hotspot",
                "message": f"{worst_day} has the highest cancellation activity, with {worst_count} cancellation(s) in this range.",
                "tone": "warning",
            })

        return {
            "range": resolved_range.model_dump(mode="json"),
            "insights": insights,
        }

    @staticmethod
    def _count_back_to_back(meetings: list[Meeting]) -> int:
        by_day: dict[date, list[Meeting]] = defaultdict(list)
        for m in meetings:
            by_day[m.start_time.date()].append(m)

        count = 0
        for day_meetings in by_day.values():
            ordered = sorted(day_meetings, key=lambda m: m.start_time)
            for prev, curr in zip(ordered, ordered[1:]):
                gap = (curr.start_time - prev.end_time).total_seconds() / 60
                if 0 <= gap < BACK_TO_BACK_GAP_MINUTES:
                    count += 1
        return count

    # ---- Export ------------------------------------------------------------

    @staticmethod
    def get_export_rows(
        db: Session,
        current_user: User,
        resolved_range: ResolvedRange,
    ) -> tuple[list[str], list[list]]:
        """
        Shared tabular data for CSV/XLSX export: the same daily trend
        used by /overview, plus a one-row summary. Returns
        (headers, rows) so app/api/analytics_routes.py can format it
        either way without duplicating the aggregation.
        """
        overview = AnalyticsService.get_overview(db, current_user, resolved_range)

        headers = ["Date", "Upcoming", "Completed", "Cancelled", "Rescheduled"]
        rows = [
            [p["date"], p["upcoming"], p["completed"], p["cancelled"], p["rescheduled"]]
            for p in overview["trend_daily"]
        ]

        rows.append([])
        rows.append(["Summary metric", "Value"])
        rows.append(["Average meeting duration (minutes)", overview["duration"]["average_minutes"]])
        rows.append(["Median meeting duration (minutes)", overview["duration"]["median_minutes"]])
        rows.append(["Longest meeting (minutes)", overview["duration"]["longest_minutes"]])
        rows.append(["Shortest meeting (minutes)", overview["duration"]["shortest_minutes"]])
        rows.append(["Total meeting hours", overview["duration"]["total_hours"]])
        rows.append(["Calendar utilization (%)", overview["utilization"]["utilization_pct"]])
        rows.append(["Productivity score", overview["productivity"]["productivity_score"]])

        return headers, rows


def _user_zoneinfo_by_name(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("UTC")


def _hour_slot_label(moment: datetime) -> str:
    hour = moment.hour
    return f"{hour:02d}:00-{(hour + 1) % 24:02d}:00"
