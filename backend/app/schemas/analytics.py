from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class KPIResponse(BaseModel):
    meetings_scheduled: int
    conflicts_avoided: int
    time_saved_minutes: int

    model_config = ConfigDict(from_attributes=True)


# ---- Analytics Dashboard Extension --------------------------------------

DateRangeKey = Literal[
    "today", "7d", "30d", "90d", "this_month", "last_month", "custom",
]

# Kept as a plain tuple (not enforced via the Literal above at the
# FastAPI route boundary) so an invalid `range` value produces the
# service's own 400 with a helpful message, rather than FastAPI's
# generic 422 - see app/api/analytics_routes.py.
DATE_RANGE_KEYS: tuple[str, ...] = (
    "today", "7d", "30d", "90d", "this_month", "last_month", "custom",
)


class ResolvedRange(BaseModel):
    start: datetime
    end: datetime


class TrendPoint(BaseModel):
    date: str
    upcoming: int
    completed: int
    cancelled: int
    rescheduled: int


class DurationStats(BaseModel):
    average_minutes: float
    median_minutes: float
    longest_minutes: int
    shortest_minutes: int
    total_hours: float
    average_daily_minutes: float


class UtilizationStats(BaseModel):
    booked_hours: float
    available_hours: float
    utilization_pct: float
    free_pct: float


class ProductivityStats(BaseModel):
    meeting_time_minutes: int
    focus_time_minutes: int
    deep_work_minutes: int
    average_meetings_per_day: float
    productivity_score: int
    meeting_load_score: int


class OverviewResponse(BaseModel):
    range: ResolvedRange
    trend_daily: list[TrendPoint]
    trend_weekly: list[TrendPoint]
    trend_monthly: list[TrendPoint]
    duration: DurationStats
    utilization: UtilizationStats
    productivity: ProductivityStats


class RescheduleAnalyticsResponse(BaseModel):
    range: ResolvedRange
    total_rescheduled: int
    reschedule_rate_pct: float
    busiest_reschedule_day: str | None
    most_common_time_slot: str | None


class CancellationAnalyticsResponse(BaseModel):
    range: ResolvedRange
    cancellation_rate_pct: float
    cancelled_count: int
    cancelled_by_organizer_count: int
    cancelled_by_participant_count: int
    trend_daily: list[dict]


class ChannelNotificationStats(BaseModel):
    sent: int
    failed: int
    success_pct: float


class NotificationAnalyticsResponse(BaseModel):
    range: ResolvedRange
    by_channel: dict[str, ChannelNotificationStats]
    overall_success_pct: float


class IntegrationAnalyticsResponse(BaseModel):
    range: ResolvedRange
    google_synced_count: int
    outlook_synced_count: int
    zoom_meetings_count: int
    teams_meetings_count: int
    connected_users: dict[str, int]
    total_users: int


class ResourceUsage(BaseModel):
    resource_id: int
    name: str
    booking_count: int
    booked_hours: float
    utilization_pct: float


class ResourceAnalyticsResponse(BaseModel):
    range: ResolvedRange
    most_used: ResourceUsage | None
    least_used: ResourceUsage | None
    average_utilization_pct: float
    virtual_meeting_count: int
    physical_meeting_count: int


class GuestAnalyticsResponse(BaseModel):
    range: ResolvedRange
    internal_meeting_count: int
    external_meeting_count: int
    guest_domains: list[dict]
    top_companies: list[dict]


class DepartmentCount(BaseModel):
    department: str
    meeting_count: int
    user_count: int


class TimezoneCount(BaseModel):
    timezone: str
    user_count: int


class TeamAnalyticsResponse(BaseModel):
    range: ResolvedRange
    by_department: list[DepartmentCount]
    by_timezone: list[TimezoneCount]
    total_users: int
    users_with_department_set: int


class Insight(BaseModel):
    id: str
    message: str
    tone: Literal["info", "positive", "warning"]


class InsightsResponse(BaseModel):
    range: ResolvedRange
    insights: list[Insight]
