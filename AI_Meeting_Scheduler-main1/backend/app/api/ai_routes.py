"""
AI endpoints — text scheduling, meeting summary, and follow-up generation.

All AI output is validated by Pydantic schemas before any application
service method is called. No endpoint writes to the database directly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.ai import (
    FollowUpDraftResponse,
    MeetingNotesRequest,
    MeetingSummaryResponse,
    TextScheduleRequest,
)
from app.schemas.scheduler import ScheduleMeetingResponse
from app.services.ai_meeting_service import AIMeetingService

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)

# Sole authoritative cap on the audio FILE itself, enforced only by the
# bounded read loop below. Request Content-Length is never inspected -
# on a multipart request it measures the whole request body (boundaries,
# headers, other fields), not just the file part, so it cannot be used
# as an upload-size check without risking false rejection of a
# genuinely valid recording.
MAX_VOICE_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

VOICE_UPLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB

# Real EBML/Matroska container magic number. Confirms a file declared
# as audio/webm at least starts like a genuine WebM container - it
# does NOT prove the file is complete, decodable, or actually carries
# an Opus audio track.
_WEBM_EBML_MAGIC = b"\x1a\x45\xdf\xa3"

_ALLOWED_AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/m4a",
    "audio/mp4",
    "audio/aac",
}


@router.post(
    "/schedule-text",
    response_model=ScheduleMeetingResponse,
    status_code=201,
    summary="Schedule a meeting from natural language",
)
def schedule_from_text(
    body: TextScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Convert a natural-language scheduling request into a confirmed
    meeting. The AI extracts the intent; all standard availability and
    conflict checks run through the existing SchedulerService.
    """
    return AIMeetingService.schedule_from_text(
        db=db,
        text=body.text,
        current_user=current_user,
    )


@router.post(
    "/schedule-voice",
    response_model=ScheduleMeetingResponse,
    status_code=201,
    summary="Schedule a meeting from a spoken audio request",
)
async def schedule_from_voice(
    audio: UploadFile = File(
        ...,
        description=(
            "A short audio recording of a spoken scheduling request, "
            "e.g. 'Schedule a product meeting tomorrow at 11 AM with "
            "the engineering team.' Supported formats: mp3, wav, "
            "webm, ogg, m4a/mp4, aac."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Voice counterpart to POST /ai/schedule-text: the audio is
    transcribed by Gemini, then the transcript is run through the
    exact same parsing/validation/scheduling pipeline as the text
    endpoint - conflict detection, availability checks, and Google
    Calendar sync all behave identically either way. Only ever
    creates a meeting, same as the text endpoint - no query/update/
    cancel dispatch.
    """
    # Real browsers always attach parameters to the recorded audio's
    # MIME type - e.g. MediaRecorder produces "audio/webm;codecs=opus",
    # never the bare "audio/webm". Only the base type (before ";") is
    # meaningful for format support.
    base_content_type = (audio.content_type or "").split(";")[0].strip()

    if base_content_type not in _ALLOWED_AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported audio format: {audio.content_type!r}. "
                f"Supported formats: mp3, wav, webm, ogg, m4a/mp4, aac."
            ),
        )

    # Bounded read: the sole authoritative size enforcement for V1 - no
    # Content-Length check of any kind precedes this. Reads in fixed
    # chunks and aborts the instant the running total exceeds the cap,
    # rather than buffering an unbounded body first. The chunk that
    # would push the total over the cap is never appended. The route
    # owns explicit close() on every exit path via this one
    # unconditional finally, rather than relying only on implicit
    # end-of-request cleanup.
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        while True:
            chunk = await audio.read(VOICE_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_VOICE_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        f"Audio file too large "
                        f"(max {MAX_VOICE_UPLOAD_BYTES // (1024 * 1024)} MB)."
                    ),
                )
            chunks.append(chunk)
    finally:
        await audio.close()

    audio_bytes = b"".join(chunks)

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty.",
        )

    # Cheap container check for the webm case only - confirms the
    # declared type matches the real EBML/Matroska magic number before
    # spending a Gemini call on it. Does not prove the file is
    # complete, decodable, or genuinely carries an Opus audio track.
    if base_content_type == "audio/webm" and not audio_bytes.startswith(
        _WEBM_EBML_MAGIC
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded file is not a valid WebM container.",
        )

    return AIMeetingService.schedule_from_voice(
        db=db,
        audio_bytes=audio_bytes,
        mime_type=base_content_type,
        current_user=current_user,
    )


@router.post(
    "/meetings/{meeting_id}/summary",
    response_model=MeetingSummaryResponse,
    summary="Summarise meeting notes and extract action items",
)
def summarize_meeting(
    meeting_id: int,
    body: MeetingNotesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a concise structured summary and extract action items from
    the supplied meeting notes or transcript. The authenticated user
    must be the meeting owner or a registered participant.

    On success, the notes, summary, and action items are persisted
    (overwriting any prior generation for this meeting) via
    MeetingIntelligenceService. See GET /meetings/{meeting_id}/notes,
    /summary, and /action-items to read persisted records afterward.
    """
    return AIMeetingService.summarize_meeting(
        db=db,
        meeting_id=meeting_id,
        notes=body.notes,
        current_user=current_user,
    )


@router.post(
    "/meetings/{meeting_id}/follow-up",
    response_model=FollowUpDraftResponse,
    summary="Generate a follow-up email draft",
)
def generate_follow_up(
    meeting_id: int,
    body: MeetingNotesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a professional follow-up email draft based on the meeting
    details and supplied notes. The email is NOT sent automatically —
    only the draft is returned. The authenticated user must be the
    meeting owner or a registered participant.
    """
    return AIMeetingService.generate_follow_up(
        db=db,
        meeting_id=meeting_id,
        notes=body.notes,
        current_user=current_user,
    )
