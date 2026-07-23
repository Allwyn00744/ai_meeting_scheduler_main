from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

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

from app.core.config import settings
from app.core.exception_handlers import (
    global_exception_handler,
    integrity_error_handler,
)

app = FastAPI(
    title="AI Meeting Scheduler API",
    version="1.0.0"
)

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


# Root Endpoint
@app.get("/")
def root():
    return {
        "message": "Welcome to AI Meeting Scheduler API"
    }


# Liveness/readiness probe for container orchestration (Docker healthcheck).
@app.get("/health")
def health():
    return {"status": "ok"}


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
