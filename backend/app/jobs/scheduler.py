"""
Background job scheduler (APScheduler). Currently one job:
mark_completed_meetings, which fixes a real, previously-latent gap -
Meeting.status is set to "scheduled" on creation and (as of this
session) "cancelled" on delete, but nothing anywhere ever transitions
it to "completed". Several existing UI/analytics numbers that key off
status == "completed" have therefore always read zero in practice.

Runs under an AsyncIOScheduler, started from app/main.py's lifespan
context manager. Disabled under `python -m unittest` (see
_running_under_unittest below) for the same reason rate limiting is -
app.main is imported once and shared across 25+ test files/TestClient
instances in a single process; leaving a live scheduler thread/task
running across all of them serves no purpose in tests and risks
"event loop is closed" noise as short-lived test event loops come and
go. tests/test_background_jobs.py calls mark_completed_meetings()
directly instead, which is what actually needs coverage.
"""
import logging
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.database import SessionLocal
from app.models.meeting import Meeting

logger = logging.getLogger(__name__)

MARK_COMPLETED_INTERVAL_MINUTES = 5

_running_under_unittest = "unittest" in sys.modules


def mark_completed_meetings() -> int:
    """
    Best-effort: opens its own independent session (mirrors
    NotificationLogService.try_record), never raises - a failure here
    must never crash the scheduler loop or take the process down.
    Returns the number of meetings updated (0 on failure).
    """
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        updated = (
            db.query(Meeting)
            .filter(
                Meeting.status == "scheduled",
                Meeting.end_time < now,
            )
            .update(
                {"status": "completed"},
                synchronize_session=False,
            )
        )
        db.commit()

        if updated:
            logger.info(
                "Marked %s meeting(s) as completed.",
                updated,
            )

        return updated
    except Exception:
        db.rollback()
        logger.exception("Failed to mark completed meetings.")
        return 0
    finally:
        db.close()


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        mark_completed_meetings,
        trigger="interval",
        minutes=MARK_COMPLETED_INTERVAL_MINUTES,
        id="mark_completed_meetings",
        # Also runs once immediately at startup rather than waiting a
        # full interval for the first pass.
        next_run_time=datetime.now(timezone.utc),
    )
    return scheduler


def start_scheduler() -> AsyncIOScheduler | None:
    """Returns None (and starts nothing) under a test run - see module docstring."""
    if _running_under_unittest:
        return None

    scheduler = create_scheduler()
    scheduler.start()
    logger.info(
        "Background job scheduler started. mark_completed_meetings "
        "runs every %s minute(s).",
        MARK_COMPLETED_INTERVAL_MINUTES,
    )
    return scheduler
