"""
AIMeetingService — orchestration layer for AI-assisted meeting features.

Responsibilities:
  - Build prompts with safe, non-secret context.
  - Resolve the authenticated user's timezone and current datetime.
  - Call GeminiService for model inference.
  - Validate AI output via Pydantic schemas (AISchedulingIntent, etc.).
  - Verify meeting existence and user authorisation.
  - Convert validated AI intent into an existing ScheduleMeetingRequest.
  - Delegate actual scheduling to SchedulerService.

Must NOT:
  - Write to the database directly.
  - Bypass existing business rules (conflict detection, availability,
    participant validation, Google Calendar integration).
  - Expose raw Gemini responses or provider error details to callers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.user_repository import UserRepository
from app.schemas.ai import (
    AISchedulingIntent,
    FollowUpDraftResponse,
    GeneratedMeetingSummary,
    MAX_SCHEDULING_TEXT_LENGTH,
    MeetingSummaryResponse,
)
from app.schemas.scheduler import ScheduleMeetingRequest
from app.services.gemini_service import GeminiService
from app.services.meeting_intelligence_service import (
    MeetingIntelligenceService,
)
from app.services.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)


class AIMeetingService:
    """Stateless orchestration service for AI meeting features."""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_meeting_authorized(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Fetch a meeting and verify the current user is either the owner
        or a registered participant. Raises 404 / 403 as appropriate.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found.",
            )

        is_owner = meeting.owner_id == current_user.id
        is_participant = (
            MeetingParticipantRepository.get_by_meeting_and_user(
                db, meeting_id, current_user.id
            )
            is not None
        )

        if not is_owner and not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorised to access this meeting.",
            )

        return meeting

    @staticmethod
    def _now_in_user_tz(user_timezone: str) -> tuple[datetime, str]:
        """
        Return (aware_datetime, human_readable_string) for the user's
        timezone. Falls back to UTC if the timezone string is invalid.

        Uses the stdlib zoneinfo module (Python 3.9+).
        """
        try:
            import zoneinfo  # noqa: PLC0415

            tz = zoneinfo.ZoneInfo(user_timezone)
            now_local = datetime.now(tz)
            formatted = now_local.strftime("%Y-%m-%dT%H:%M:%S (%A)")
            return now_local, formatted
        except Exception:
            logger.warning(
                "Invalid user timezone '%s', falling back to UTC.",
                user_timezone,
            )
            now_utc = datetime.now(timezone.utc)
            formatted = now_utc.strftime("%Y-%m-%dT%H:%M:%S (%A)")
            return now_utc, formatted

    @staticmethod
    def _verify_participants_exist(
        db: Session,
        participant_ids: list[int],
    ) -> None:
        """
        Check every extracted participant ID exists in the database.
        Raises 404 for the first missing ID found.

        The SchedulerService enforces duplicate/owner-as-participant
        rules later — this method only checks existence.
        """
        for uid in participant_ids:
            user = UserRepository.get_user_by_id(db, uid)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Participant with user ID {uid} does not exist.",
                )

    @staticmethod
    def _resolve_recipients(
        db: Session,
        participant_ids: list[int],
        extracted_emails: list[str],
    ) -> tuple[list[int], list[str]]:
        """
        Authoritatively resolve Gemini-extracted email addresses
        against the users table (PostgreSQL is the source of truth,
        never Gemini's own judgement): an email belonging to a
        registered user is merged into participant_ids, everything
        else remains an external guest email.

        extracted_emails is expected to already be normalized/deduped
        (AISchedulingIntent does this). Both returned lists are
        deduplicated - participant_ids by user id, emails are simply
        passed through since they came in already deduped and a
        resolved-to-participant email is never also kept as a guest.
        """
        resolved_participant_ids = list(participant_ids)
        seen_ids = set(resolved_participant_ids)
        external_guest_emails: list[str] = []

        for email in extracted_emails:
            user = UserRepository.get_user_by_email_ci(db, email)

            if user is not None:
                if user.id not in seen_ids:
                    seen_ids.add(user.id)
                    resolved_participant_ids.append(user.id)
            else:
                external_guest_emails.append(email)

        return resolved_participant_ids, external_guest_emails

    # ------------------------------------------------------------------
    # 1. AI Text Scheduling
    # ------------------------------------------------------------------

    @staticmethod
    def schedule_from_voice(
        db: Session,
        audio_bytes: bytes,
        mime_type: str,
        current_user: User,
    ) -> dict:
        """
        Transcribe spoken audio, then hand the transcript to the
        existing schedule_from_text exactly as if it had been typed.
        No create-vs-query/update/cancel dispatch lives here — voice
        scheduling in V1 only ever creates a meeting, mirroring
        exactly what the text endpoint does today. Calls
        schedule_from_text exactly once; no scheduling logic is
        duplicated here.

        The transcript never passes through TextScheduleRequest's own
        Pydantic max_length check (it isn't a JSON request body), so
        the same MAX_SCHEDULING_TEXT_LENGTH bound is enforced here
        explicitly instead — not silently skipped, not truncated.
        """
        transcript = GeminiService.transcribe_audio(audio_bytes, mime_type)

        if len(transcript) > MAX_SCHEDULING_TEXT_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The transcribed request is too long to process "
                    f"(max {MAX_SCHEDULING_TEXT_LENGTH} characters). "
                    "Please make a shorter recording."
                ),
            )

        return AIMeetingService.schedule_from_text(
            db, transcript, current_user
        )

    @staticmethod
    def schedule_from_text(
        db: Session,
        text: str,
        current_user: User,
    ) -> dict:
        """
        Parse a natural-language scheduling request, validate the
        extracted intent, then delegate to SchedulerService.

        Flow:
          1. Build prompt with current datetime and user timezone.
          2. Call GeminiService.generate_json().
          3. Check for ambiguity signal from Gemini → 422.
          4. Validate raw dict with AISchedulingIntent → 422.
          5. Verify participant IDs exist → 404.
          6. Convert intent to ScheduleMeetingRequest → 422.
          7. Delegate to SchedulerService.schedule_meeting().
        """
        user_tz = current_user.timezone or "UTC"
        _, now_formatted = AIMeetingService._now_in_user_tz(user_tz)

        prompt = (
            "You are a scheduling assistant. Parse the user's scheduling "
            "request and return a JSON object.\n\n"
            f"Current datetime: {now_formatted}\n"
            f"User timezone: {user_tz}\n\n"
            f'User request: "{text}"\n\n'
            "Return ONLY a valid JSON object.\n\n"
            "If the request is CLEAR, use this structure:\n"
            "{\n"
            '  "status": "ok",\n'
            '  "title": "<meeting title>",\n'
            '  "description": null,\n'
            '  "start_time": "<ISO 8601 UTC, e.g. 2026-07-09T16:00:00Z>",\n'
            '  "end_time": null,\n'
            '  "duration_minutes": 60,\n'
            '  "location": null,\n'
            '  "participant_ids": [],\n'
            '  "external_guest_emails": [],\n'
            '  "repeat": false,\n'
            '  "repeat_type": null,\n'
            '  "occurrences": null\n'
            "}\n\n"
            "If the request is AMBIGUOUS or missing required info "
            "(title, date, or time), use:\n"
            "{\n"
            '  "status": "ambiguous",\n'
            '  "reason": "<explain exactly what is missing or unclear>"\n'
            "}\n\n"
            "Rules:\n"
            f"- Convert all times to UTC using the user timezone ({user_tz}).\n"
            "- Resolve relative dates (tomorrow, next Thursday) from the "
            "current datetime shown above.\n"
            "- participant_ids: ONLY include explicit integer user IDs "
            'mentioned in the request (e.g. "with user 5" → [5]). '
            "If participants are referenced by name or role only, "
            "set participant_ids to [].\n"
            "- external_guest_emails: include every email address "
            '(e.g. "guest@example.com") mentioned anywhere in the '
            "request, exactly as written. Do not invent emails. Do "
            "not try to decide whether an address belongs to a "
            "registered user or an outside guest - just extract "
            "every address you see. If none are mentioned, set "
            "external_guest_emails to [].\n"
            "- If the title is not stated, derive a concise one from "
            "the request.\n"
            "- If a duration is mentioned but no end_time, set "
            "duration_minutes; otherwise set end_time.\n"
            "- If neither end_time nor duration are stated, default "
            "duration_minutes to 60.\n"
            "- repeat_type must be 'weekly' or null.\n"
            "- occurrences must be a positive integer or null.\n"
            "- Do not invent dates, times, or participants.\n"
            "- Return ONLY the JSON object, no markdown, no explanation."
        )

        raw = GeminiService.generate_json(prompt)


        # --- Handle ambiguity signal ---
        if raw.get("status") == "ambiguous":
            reason = raw.get(
                "reason",
                "The scheduling request is incomplete or ambiguous.",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot schedule meeting: {reason}",
            )

        # Strip protocol fields before schema validation
        raw.pop("status", None)
        raw.pop("reason", None)

        # --- Validate AI output ---
        try:
            intent = AISchedulingIntent.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Gemini output failed AISchedulingIntent validation. "
                "error_count=%s",
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The scheduling request could not be parsed reliably. "
                    "Please specify the date, time, and title clearly."
                ),
            )


        # --- Resolve extracted emails against the users table ---
        # Authoritative: Gemini only extracts addresses, it never
        # decides whether one belongs to a registered user.
        participant_ids, external_guest_emails = (
            AIMeetingService._resolve_recipients(
                db, intent.participant_ids, intent.external_guest_emails
            )
        )

        # --- Verify participants exist in DB ---
        AIMeetingService._verify_participants_exist(db, participant_ids)

        # --- Convert to ScheduleMeetingRequest ---
        # end_time is guaranteed to be set by AISchedulingIntent validator.
        try:
            schedule_request = ScheduleMeetingRequest(
                title=intent.title.strip(),
                description=intent.description,
                start_time=intent.start_time,
                end_time=intent.end_time,  # type: ignore[arg-type]
                location=intent.location,
                participant_ids=participant_ids,
                external_guest_emails=external_guest_emails,
                repeat=intent.repeat,
                repeat_type=intent.repeat_type,
                occurrences=intent.occurrences,
            )
        except ValidationError as exc:
            logger.warning(
                "AI intent failed ScheduleMeetingRequest validation. "
                "error_count=%s",
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The parsed scheduling data is invalid. "
                    "Please refine your request."
                ),
            )

        # --- Delegate to existing SchedulerService ---
        # All availability checks, conflict detection, Google Calendar
        # sync, and email invites are handled inside schedule_meeting().
        return SchedulerService.schedule_meeting(
            db, schedule_request, current_user
        )

    # ------------------------------------------------------------------
    # 2. Meeting Summary + Action Items
    # ------------------------------------------------------------------

    @staticmethod
    def summarize_meeting(
        db: Session,
        meeting_id: int,
        notes: str,
        current_user: User,
    ) -> MeetingSummaryResponse:
        """
        Generate a structured summary and extract action items from the
        supplied meeting notes. The authenticated user must be the owner
        or a participant of the meeting.

        Persistence of the notes/summary/action items is delegated to
        MeetingIntelligenceService after Gemini output has been
        validated — this method still never writes to the database
        directly.
        """
        meeting = AIMeetingService._get_meeting_authorized(
            db, meeting_id, current_user
        )

        start_str = meeting.start_time.strftime("%Y-%m-%d %H:%M UTC")
        end_str = meeting.end_time.strftime("%Y-%m-%d %H:%M UTC")

        prompt = (
            "You are a meeting assistant. Summarise the following meeting "
            "notes and extract action items.\n\n"
            f"Meeting: {meeting.title}\n"
            f"Date: {start_str} – {end_str}\n\n"
            "Notes:\n"
            f"{notes}\n\n"
            "Return ONLY a valid JSON object with this exact structure:\n"
            "{\n"
            '  "summary": "<concise 2-4 sentence summary>",\n'
            '  "action_items": [\n'
            "    {\n"
            '      "task": "<specific task>",\n'
            '      "assignee": "<person responsible or null>",\n'
            '      "due_date": "<YYYY-MM-DD or null>"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Base the summary ONLY on the provided notes.\n"
            "- Do not hallucinate or invent any information.\n"
            "- Extract ONLY action items explicitly mentioned in the notes.\n"
            "- If no action items are present, return action_items as [].\n"
            "- Do not invent assignees or due dates not stated in the notes.\n"
            "- Keep the summary factual and concise.\n"
            "- Return ONLY the JSON object, no markdown, no explanation."
        )

        raw = GeminiService.generate_json(prompt)

        try:
            generated = GeneratedMeetingSummary.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Gemini summary output failed validation. "
                "meeting_id=%s error_count=%s",
                meeting_id,
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service returned an invalid summary response.",
            )

        # --- Persist notes + summary + action items ---
        # No database write happens above this point. If Gemini fails
        # or its output fails validation, execution never reaches here,
        # so no partial intelligence record can ever be created.
        return MeetingIntelligenceService.persist_summary(
            db=db,
            meeting_id=meeting.id,
            notes_text=notes,
            summary_text=generated.summary,
            action_items=generated.action_items,
            current_user=current_user,
        )

    # ------------------------------------------------------------------
    # 3. Follow-up Generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_follow_up(
        db: Session,
        meeting_id: int,
        notes: str,
        current_user: User,
    ) -> FollowUpDraftResponse:
        """
        Generate a professional follow-up email draft.

        The email is NOT sent — only the draft is returned. The
        authenticated user must be the meeting owner or a participant.
        """
        meeting = AIMeetingService._get_meeting_authorized(
            db, meeting_id, current_user
        )

        start_str = meeting.start_time.strftime("%Y-%m-%d %H:%M UTC")
        end_str = meeting.end_time.strftime("%Y-%m-%d %H:%M UTC")
        # Prefer human-readable location; fall back to Meet link if set.
        location_str = (
            meeting.location
            or meeting.google_meet_link
            or "N/A"
        )

        prompt = (
            "You are a meeting assistant. Generate a professional "
            "follow-up email draft.\n\n"
            f"Meeting: {meeting.title}\n"
            f"Date: {start_str} – {end_str}\n"
            f"Location/Link: {location_str}\n\n"
            "Notes:\n"
            f"{notes}\n\n"
            "Return ONLY a valid JSON object with this exact structure:\n"
            "{\n"
            '  "email_subject": "<concise professional subject line>",\n'
            '  "email_body": "<professional follow-up email in plain text>"\n'
            "}\n\n"
            "Rules:\n"
            "- Base content ONLY on the provided meeting data and notes.\n"
            "- Do not invent information not present in the notes or "
            "meeting details.\n"
            "- Summarise key outcomes and next steps.\n"
            "- Use plain text only — no HTML tags.\n"
            "- Avoid placeholder brackets like [name] in the body.\n"
            "- Return ONLY the JSON object, no markdown, no explanation."
        )

        raw = GeminiService.generate_json(prompt)

        try:
            return FollowUpDraftResponse.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Gemini follow-up output failed validation. "
                "meeting_id=%s error_count=%s",
                meeting_id,
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service returned an invalid follow-up response.",
            )
