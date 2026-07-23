import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.jobs.scheduler import start_scheduler
from app.websocket.connection_manager import connection_manager

from app.api.user_routes import router as user_router
from app.api.auth_routes import router as auth_router
from app.api.meeting_routes import router as meeting_router
from app.api.meeting_participant_routes import router as participant_router
from app.api.availability_routes import router as availability_router
from app.api.resource_routes import router as resource_router
from app.api.scheduler_routes import router as scheduler_router
from app.api.email_routes import router as email_router
from app.api.google_routes import router as google_router
from app.api.outlook_routes import router as outlook_router
from app.api.zoom_routes import router as zoom_router
from app.api.teams_routes import router as teams_router
from app.api.slack_routes import router as slack_router
from app.api.whatsapp_routes import router as whatsapp_router
from app.api.push_routes import router as push_router
from app.api.ai_routes import router as ai_router
from app.api.meeting_intelligence_routes import (
    router as meeting_intelligence_router,
)
from app.api.meeting_note_routes import router as meeting_note_router
from app.api.meeting_transcript_routes import (
    router as meeting_transcript_router,
)
from app.api.meeting_summary_routes import router as meeting_summary_router
from app.api.meeting_action_item_routes import (
    router as meeting_action_item_router,
)
from app.api.meeting_followup_email_routes import (
    router as meeting_followup_email_router,
)
from app.api.meeting_insight_routes import (
    router as meeting_insight_router,
)
from app.api.analytics_routes import router as analytics_router
from app.api.websocket_routes import router as websocket_router
from app.api.meeting_series_routes import router as meeting_series_router

from app.core.config import settings
from app.core.exception_handlers import (
    global_exception_handler,
    integrity_error_handler,
)
from app.core.cache import redis_healthy
from app.core.logging_config import configure_logging
from app.core.rate_limit import limiter
from app.core.request_id import RequestIDMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.database import get_db

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup. start_scheduler() is a no-op (returns None) under
    # `python -m unittest` - see app/jobs/scheduler.py. The running
    # loop is captured here (lifespan runs on it) so MeetingService's
    # sync methods, executing on a worker thread, can bridge a
    # broadcast back onto it - see ConnectionManager.broadcast_to_user_sync.
    scheduler = start_scheduler()
    connection_manager.set_event_loop(asyncio.get_running_loop())

    yield

    # Shutdown
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="AI Meeting Scheduler API",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting (slowapi) - see app/core/rate_limit.py. Only the auth
# routes that opt in via @limiter.limit(...) are actually throttled;
# every other route is unaffected. The middleware only adds
# X-RateLimit-* response headers to limited routes, it does not limit
# anything on its own.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS for the React frontend. Origins come from settings
# (CORS_ORIGINS, comma-separated) and must never include "*" — this
# app sends credentials (Authorization headers), and a wildcard
# origin must never be combined with allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added last so it's the outermost layer (Starlette applies
# middleware in reverse-of-registration order) - every response,
# including ones CORS or the rate limiter reject before reaching a
# route, still gets these baseline security headers.
app.add_middleware(SecurityHeadersMiddleware)

# Outermost of all (added last) so the request ID is set before any
# other middleware or route code runs, making it available to every
# log line emitted anywhere while handling this request.
app.add_middleware(RequestIDMiddleware)


# Root Endpoint
@app.get("/")
def root():
    return {
        "message": "Welcome to AI Meeting Scheduler API"
    }


# Liveness/readiness probe for container orchestration (Docker healthcheck).
# Kept exactly as-is (existing consumer: the Dockerfile HEALTHCHECK
# instruction) - GET /health/live and /health/ready below are
# additive, more specific probes for orchestrators that distinguish
# the two (e.g. Kubernetes).
@app.get("/health")
def health():
    return {"status": "ok"}


# Liveness: is the process itself up and able to respond at all - no
# dependency checks. An orchestrator restarts the container if this
# ever fails; it must never fail just because a downstream dependency
# (database, Redis) is degraded, or a transient DB blip would trigger
# needless restarts instead of the readiness probe below correctly
# just pulling this instance out of rotation.
@app.get("/health/live")
def health_live():
    return {"status": "ok"}


# Readiness: can this instance actually serve traffic right now.
# Checks the database (required - nothing works without it) and,
# only if REDIS_URL is configured at all, Redis - an unconfigured
# Redis is a supported "caching disabled" state (see app/core/cache.py)
# and must not make an otherwise-healthy instance report not-ready.
@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    checks: dict[str, bool] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    if settings.REDIS_URL:
        checks["redis"] = redis_healthy()

    ready = all(checks.values())

    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready else "not ready", "checks": checks},
    )


# Specific handlers are registered before the catch-all Exception
# handler so FastAPI matches IntegrityError to the dedicated 409
# handler instead of falling through to the generic 500 handler.
app.add_exception_handler(
    IntegrityError,
    integrity_error_handler,
)
app.add_exception_handler(
    Exception,
    global_exception_handler,
)
# Register User Routes
app.include_router(user_router)
app.include_router(auth_router)
app.include_router(meeting_router)
app.include_router(participant_router)
app.include_router(availability_router)
app.include_router(resource_router)
app.include_router(scheduler_router)
app.include_router(email_router)
app.include_router(google_router)
app.include_router(outlook_router)
app.include_router(zoom_router)
app.include_router(teams_router)
app.include_router(slack_router)
app.include_router(whatsapp_router)
app.include_router(push_router)
app.include_router(ai_router)
app.include_router(meeting_intelligence_router)
app.include_router(meeting_note_router)
app.include_router(meeting_transcript_router)
app.include_router(meeting_summary_router)
app.include_router(meeting_action_item_router)
app.include_router(meeting_followup_email_router)
app.include_router(meeting_insight_router)
app.include_router(analytics_router)
app.include_router(websocket_router)
app.include_router(meeting_series_router)

# GET /metrics - Prometheus text-format exposition (request counts,
# latency histograms, in-progress requests, all broken down by
# method/path/status). No app-specific instrumentation code needed -
# this wraps every route already registered above automatically.
Instrumentator().instrument(app).expose(app, include_in_schema=False)
