import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.analytics import (
    DATE_RANGE_KEYS,
    CancellationAnalyticsResponse,
    GuestAnalyticsResponse,
    InsightsResponse,
    IntegrationAnalyticsResponse,
    KPIResponse,
    NotificationAnalyticsResponse,
    OverviewResponse,
    ResourceAnalyticsResponse,
    RescheduleAnalyticsResponse,
    TeamAnalyticsResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)

_RANGE_DESCRIPTION = "One of: " + ", ".join(DATE_RANGE_KEYS)


@router.get(
    "/kpis",
    response_model=KPIResponse,
)
def get_kpis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AnalyticsService.get_kpis(db, current_user)


def _resolve_range(
    current_user: User,
    range: str,
    start: date | None,
    end: date | None,
):
    """
    `range` is deliberately a plain str (not a FastAPI/Pydantic
    Literal) so an unrecognized value produces
    AnalyticsService.resolve_date_range's own 400 with a helpful
    message, rather than a generic 422 from automatic enum validation.
    """
    return AnalyticsService.resolve_date_range(
        range, start, end, current_user.timezone,
    )


@router.get(
    "/overview",
    response_model=OverviewResponse,
)
def get_overview(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_overview(db, current_user, resolved)


@router.get(
    "/reschedule",
    response_model=RescheduleAnalyticsResponse,
)
def get_reschedule_analytics(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_reschedule_analytics(db, current_user, resolved)


@router.get(
    "/cancellations",
    response_model=CancellationAnalyticsResponse,
)
def get_cancellation_analytics(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_cancellation_analytics(db, current_user, resolved)


@router.get(
    "/notifications",
    response_model=NotificationAnalyticsResponse,
)
def get_notification_analytics(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_notification_analytics(db, current_user, resolved)


@router.get(
    "/integrations",
    response_model=IntegrationAnalyticsResponse,
)
def get_integration_analytics(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_integration_analytics(db, current_user, resolved)


@router.get(
    "/resources",
    response_model=ResourceAnalyticsResponse,
)
def get_resource_analytics(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_resource_analytics(db, current_user, resolved)


@router.get(
    "/guests",
    response_model=GuestAnalyticsResponse,
)
def get_guest_analytics(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_guest_analytics(db, current_user, resolved)


@router.get(
    "/team",
    response_model=TeamAnalyticsResponse,
)
def get_team_analytics(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    The only endpoint in this router whose numbers span every user,
    not just current_user - see AnalyticsService.get_team_overview for
    exactly what that does and doesn't expose. Still requires auth
    like every other route here; it just isn't owner-scoped.
    """
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_team_overview(db, resolved)


@router.get(
    "/insights",
    response_model=InsightsResponse,
)
def get_insights(
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    return AnalyticsService.get_insights(db, current_user, resolved)


@router.get("/export")
def export_analytics(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    range: str = Query("30d", description=_RANGE_DESCRIPTION),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved = _resolve_range(current_user, range, start, end)
    headers, rows = AnalyticsService.get_export_rows(db, current_user, resolved)

    if format == "xlsx":
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Analytics"
        sheet.append(headers)
        for row in rows:
            sheet.append(row if row else [])

        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": (
                    "attachment; filename=analytics-export.xlsx"
                ),
            },
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row if row else [])

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=analytics-export.csv",
        },
    )
