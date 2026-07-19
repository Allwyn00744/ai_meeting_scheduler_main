import logging
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cache import (
    cache_delete,
    cache_delete_prefix,
    kpis_key,
    meetings_list_prefix,
)
from app.models.external_meeting_guest import ExternalMeetingGuest
from app.models.meeting import Meeting
from app.models.meeting_participant import MeetingParticipant
from app.models.user import User

from app.repositories.external_meeting_guest_repository import (
    ExternalMeetingGuestRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.user_repository import UserRepository
from app.repositories.resource_repository import ResourceRepository
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)

from app.schemas.meeting import MeetingUpdate
from app.schemas.scheduler import (
    AutoRescheduleResponse,
    ScheduleMeetingRequest,
    SuggestSlotsResponse,
    SuggestedSlot,
)

from app.services.analytics_service import (
    EVENT_CONFLICT_BLOCKED_OWNER,
    EVENT_CONFLICT_BLOCKED_PARTICIPANT,
    EVENT_CONFLICT_BLOCKED_RESOURCE,
    AnalyticsService,
)
from app.services.email_service import EmailService
from app.services.conflict_service import ConflictService
from app.services.availability_service import AvailabilityService
from app.services.external_guest_service import ExternalGuestService
from app.services.google_calendar_service import GoogleCalendarService
from app.services.meeting_notification_service import (
    MeetingNotificationService,
)
from app.services.outlook_calendar_service import OutlookCalendarService
from app.services.slack_notification_service import SlackNotificationService
from app.services.teams_meeting_service import TeamsMeetingService
from app.services.zoom_calendar_service import ZoomCalendarService
from app.services.meeting_service import MeetingService


logger = logging.getLogger(__name__)

# How many consecutive one-hour slots suggest_slots will try before
# giving up and telling the caller no slot was found, instead of
# silently returning None (which previously broke the declared
# response_model whenever the search was exhausted).
MAX_SLOT_ATTEMPTS = 8

# suggest_reschedule_slots: fixed candidate step, default search
# window, and cap on how many suggestions are returned.
RESCHEDULE_SEARCH_INTERVAL_MINUTES = 15
DEFAULT_RESCHEDULE_WINDOW_DAYS = 7
MAX_RESCHEDULE_SUGGESTIONS = 5


class SchedulerService:
    """
    Handles intelligent meeting scheduling.
    """

    @staticmethod
    def _validate_participants(db: Session, current_user: User, meeting):
        if len(meeting.participant_ids) != len(
            set(meeting.participant_ids)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Duplicate participants are not allowed.",
            )

        if current_user.id in meeting.participant_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Meeting owner cannot be a participant.",
            )

        for user_id in meeting.participant_ids:
            user = UserRepository.get_user_by_id(
                db,
                user_id,
            )

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {user_id} does not exist.",
                )

    @staticmethod
    def _cleanup_created_occurrences(
        db: Session,
        created_meeting_ids: list[int],
    ):
        """
        Best-effort compensation for a recurring-series request that
        fails partway through creating its occurrences. Deletes any
        meetings already created in this batch (participant rows are
        removed automatically via ON DELETE CASCADE) and attempts to
        remove their Google Calendar events too, so a failed request
        doesn't leave a silent partial series behind.

        This is a compensating cleanup, not a database transaction:
        PostgreSQL and Google Calendar are two separate systems and
        this method does not make the overall operation atomic across
        both.
        """
        for meeting_id in created_meeting_ids:
            meeting = MeetingRepository.get_by_id(db, meeting_id)

            if meeting is None:
                continue

            if meeting.google_event_id:
                try:
                    GoogleCalendarService.delete_google_calendar_event(
                        db=db,
                        meeting=meeting,
                    )
                except HTTPException:
                    logger.warning(
                        "Cleanup: failed to delete Google Calendar "
                        "event for meeting_id=%s during rollback of "
                        "a failed recurring series.",
                        meeting_id,
                    )

            if meeting.outlook_event_id:
                try:
                    OutlookCalendarService.delete_outlook_calendar_event(
                        db=db,
                        meeting=meeting,
                    )
                except HTTPException:
                    logger.warning(
                        "Cleanup: failed to delete Outlook Calendar "
                        "event for meeting_id=%s during rollback of "
                        "a failed recurring series.",
                        meeting_id,
                    )
                # No separate Microsoft Teams cleanup: a Teams meeting
                # isn't its own resource, it's this same Outlook event
                # with isOnlineMeeting/onlineMeetingProvider set, so
                # deleting the event above removes it on Microsoft's
                # side too.

            if meeting.zoom_meeting_id:
                try:
                    ZoomCalendarService.delete_zoom_meeting(
                        db=db,
                        meeting=meeting,
                    )
                except HTTPException:
                    logger.warning(
                        "Cleanup: failed to delete Zoom meeting for "
                        "meeting_id=%s during rollback of a failed "
                        "recurring series.",
                        meeting_id,
                    )

            try:
                MeetingRepository.delete(db, meeting)
            except IntegrityError:
                db.rollback()
                logger.error(
                    "Cleanup: failed to delete meeting_id=%s during "
                    "rollback of a failed recurring series.",
                    meeting_id,
                )

    @staticmethod
    def schedule_meeting(
        db: Session,
        meeting: ScheduleMeetingRequest,
        current_user: User,
    ):
        """
        Schedule a meeting after validating all occurrences.
        """

        # ---------------------------------------
        # Step 1: Validate request participants
        # ---------------------------------------

        SchedulerService._validate_participants(db, current_user, meeting)

        # ---------------------------------------
        # Step 1.5: Resolve external guests once
        # ---------------------------------------
        # Resolved before the occurrence loop, since the same guest
        # set applies to every occurrence (mirrors participant_ids).
        # Participant emails are resolved here only to exclude
        # collisions - AvailabilityService/ConflictService are never
        # called with external guest data anywhere in this method.

        participant_users = (
            UserRepository.get_users_by_ids(
                db,
                meeting.participant_ids,
            )
            if meeting.participant_ids
            else []
        )

        resolved_external_guests = ExternalGuestService.resolve_guests(
            meeting.external_guest_emails,
            current_user.email,
            [user.email for user in participant_users],
        )

        # ---------------------------------------
        # Step 2: Determine number of occurrences
        # ---------------------------------------
        # (schemas.scheduler.ScheduleMeetingRequest already validates
        # repeat_type and caps occurrences at MAX_OCCURRENCES, so this
        # only needs to read the already-validated value.)

        repeat_count = 1

        if (
            meeting.repeat
            and meeting.repeat_type == "weekly"
            and meeting.occurrences
        ):
            repeat_count = meeting.occurrences

        # ---------------------------------------
        # Step 3: Build ALL occurrences
        # ---------------------------------------

        occurrences = []

        for i in range(repeat_count):
            meeting_start = (
                meeting.start_time
                + timedelta(days=7 * i)
            )

            meeting_end = (
                meeting.end_time
                + timedelta(days=7 * i)
            )

            occurrences.append(
                (meeting_start, meeting_end)
            )

        # ---------------------------------------
        # Step 3.5: Validate the resource once
        # ---------------------------------------
        # Resource identity does not change across occurrences, so
        # existence/active-status is checked once here rather than
        # once per occurrence. Per-occurrence timing conflicts are
        # still checked separately below, since each occurrence has
        # its own time range.

        resource = None

        if meeting.resource_id is not None:
            resource = ResourceRepository.get_by_id(
                db,
                meeting.resource_id,
            )

            if resource is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Resource not found",
                )

            if not resource.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Resource '{resource.name}' is not active "
                        f"and cannot be booked."
                    ),
                )

        # ---------------------------------------
        # Step 4: Validate ALL occurrences
        # ---------------------------------------

        for index, (meeting_start, meeting_end) in enumerate(
            occurrences,
            start=1,
        ):

            # Owner conflict
            owner_conflict, owner_meeting = (
                ConflictService.check_user_conflict(
                    db,
                    current_user.id,
                    meeting_start,
                    meeting_end,
                )
            )

            if owner_conflict:
                AnalyticsService.try_record_event(
                    current_user.id,
                    EVENT_CONFLICT_BLOCKED_OWNER,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Occurrence {index} conflicts with "
                        f"'{owner_meeting.title}'."
                    ),
                )

            # Owner availability
            if not AvailabilityService.is_user_available(
                db,
                current_user.id,
                meeting_start,
                meeting_end,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Occurrence {index} is outside "
                        "your available working hours."
                    ),
                )

            # Participant conflicts
            conflict, user_id, conflict_meeting = (
                ConflictService.check_all_participants(
                    db,
                    meeting.participant_ids,
                    meeting_start,
                    meeting_end,
                )
            )

            if conflict:
                AnalyticsService.try_record_event(
                    current_user.id,
                    EVENT_CONFLICT_BLOCKED_PARTICIPANT,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Occurrence {index}: participant "
                        f"{user_id} has a scheduling conflict "
                        f"({conflict_meeting.title})."
                    ),
                )

            # Participant availability
            for user_id in meeting.participant_ids:

                if not AvailabilityService.is_user_available(
                    db,
                    user_id,
                    meeting_start,
                    meeting_end,
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Occurrence {index}: participant "
                            f"{user_id} is not available."
                        ),
                    )

            # Resource conflict (existence/active already validated
            # once in Step 3.5 above; only the per-occurrence timing
            # overlap is checked here).
            if resource is not None:
                resource_conflict, conflicting_meeting = (
                    ConflictService.check_resource_conflict(
                        db,
                        meeting.resource_id,
                        meeting_start,
                        meeting_end,
                    )
                )

                if resource_conflict:
                    AnalyticsService.try_record_event(
                        current_user.id,
                        EVENT_CONFLICT_BLOCKED_RESOURCE,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Occurrence {index}: resource "
                            f"'{resource.name}' is already booked "
                            f"for '{conflicting_meeting.title}'."
                        ),
                    )

        # ---------------------------------------
        # Step 5: Create only after ALL pass
        # ---------------------------------------

        created_meetings = []

        try:
            for meeting_start, meeting_end in occurrences:

                db_meeting = Meeting(
                    title=meeting.title,
                    description=meeting.description,
                    start_time=meeting_start,
                    end_time=meeting_end,
                    location=meeting.location,
                    owner_id=current_user.id,
                    resource_id=meeting.resource_id,
                )

                db_meeting = MeetingRepository.create(
                    db,
                    db_meeting,
                )

                participants = []

                for user_id in meeting.participant_ids:
                    participants.append(
                        MeetingParticipant(
                            meeting_id=db_meeting.id,
                            user_id=user_id,
                            status="Pending",
                        )
                    )

                if participants:
                    MeetingParticipantRepository.create_many(
                        db,
                        participants,
                    )

                if resolved_external_guests:
                    ExternalMeetingGuestRepository.create_many(
                        db,
                        [
                            ExternalMeetingGuest(
                                meeting_id=db_meeting.id,
                                email=email,
                            )
                            for email in resolved_external_guests
                        ],
                    )

                created_meetings.append(db_meeting.id)

                # Google Calendar sync is a best-effort side effect,
                # deliberately isolated from the database transaction
                # above: PostgreSQL and Google Calendar are two
                # separate systems with no distributed transaction
                # between them. A Calendar failure here does not
                # cause the meeting occurrence itself to be rolled
                # back or the series to be aborted.
                try:
                    event = (
                        GoogleCalendarService
                        .create_google_calendar_event(
                            db=db,
                            user_id=current_user.id,
                            title=db_meeting.title,
                            description=db_meeting.description or "",
                            start_time=db_meeting.start_time,
                            end_time=db_meeting.end_time,
                            location=db_meeting.location,
                            attendee_emails=resolved_external_guests,
                        )
                    )

                    db_meeting.google_event_id = event.get("id")
                    db_meeting.google_event_link = event.get(
                        "htmlLink"
                    )
                    db_meeting.google_meet_link = event.get(
                        "hangoutLink"
                    )

                    db.commit()
                    db.refresh(db_meeting)

                    logger.info(
                        "Google Calendar event created successfully. "
                        "meeting_id=%s meet_link_created=%s",
                        db_meeting.id,
                        event.get("hangoutLink") is not None,
                    )

                except Exception:
                    logger.exception(
                        "Google Calendar integration failed. "
                        "meeting_id=%s",
                        db_meeting.id,
                    )

                # Outlook Calendar sync, parallel to the Google block
                # above - each provider is optional and independent.
                if OutlookCalendarService.is_outlook_connected(
                    db,
                    current_user.id,
                ):
                    try:
                        outlook_event = (
                            OutlookCalendarService
                            .create_outlook_calendar_event(
                                db=db,
                                user_id=current_user.id,
                                title=db_meeting.title,
                                description=db_meeting.description or "",
                                start_time=db_meeting.start_time,
                                end_time=db_meeting.end_time,
                                location=db_meeting.location,
                                attendee_emails=resolved_external_guests,
                            )
                        )

                        db_meeting.outlook_event_id = outlook_event.get(
                            "id"
                        )
                        db_meeting.outlook_event_link = outlook_event.get(
                            "webLink"
                        )

                        db.commit()
                        db.refresh(db_meeting)

                        logger.info(
                            "Outlook Calendar event created "
                            "successfully. meeting_id=%s",
                            db_meeting.id,
                        )

                    except Exception:
                        logger.exception(
                            "Outlook Calendar integration failed. "
                            "meeting_id=%s",
                            db_meeting.id,
                        )

                # Microsoft Teams sync, parallel to the Google/Outlook
                # blocks above - but it never creates its own
                # resource, it only extends the Outlook event just
                # created, so it only runs when that block succeeded
                # for this occurrence.
                if db_meeting.outlook_event_id:
                    try:
                        teams_event = (
                            TeamsMeetingService.enable_teams_meeting(
                                db=db,
                                user_id=current_user.id,
                                event_id=db_meeting.outlook_event_id,
                            )
                        )

                        db_meeting.teams_join_url = (
                            teams_event.get("onlineMeeting") or {}
                        ).get("joinUrl")

                        db.commit()
                        db.refresh(db_meeting)

                        logger.info(
                            "Microsoft Teams meeting enabled "
                            "successfully. meeting_id=%s",
                            db_meeting.id,
                        )

                    except Exception:
                        logger.exception(
                            "Microsoft Teams integration failed. "
                            "meeting_id=%s",
                            db_meeting.id,
                        )

                # Zoom Meeting sync, parallel to the Google/Outlook/
                # Teams blocks above - each provider is optional and
                # independent.
                if ZoomCalendarService.is_zoom_connected(
                    db,
                    current_user.id,
                ):
                    try:
                        zoom_meeting = (
                            ZoomCalendarService.create_zoom_meeting(
                                db=db,
                                user_id=current_user.id,
                                title=db_meeting.title,
                                description=db_meeting.description or "",
                                start_time=db_meeting.start_time,
                                end_time=db_meeting.end_time,
                            )
                        )

                        db_meeting.zoom_meeting_id = str(
                            zoom_meeting.get("id")
                        )
                        db_meeting.zoom_join_url = zoom_meeting.get(
                            "join_url"
                        )
                        db_meeting.zoom_start_url = zoom_meeting.get(
                            "start_url"
                        )

                        db.commit()
                        db.refresh(db_meeting)

                        logger.info(
                            "Zoom meeting created successfully. "
                            "meeting_id=%s",
                            db_meeting.id,
                        )

                    except Exception:
                        logger.exception(
                            "Zoom Meeting integration failed. "
                            "meeting_id=%s",
                            db_meeting.id,
                        )

        except IntegrityError:
            db.rollback()
            logger.error(
                "Recurring meeting series creation failed partway "
                "through. Rolling back %s already-created "
                "occurrence(s).",
                len(created_meetings),
            )
            SchedulerService._cleanup_created_occurrences(
                db,
                created_meetings,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Failed to create the recurring meeting series "
                    "due to a database conflict. No occurrences were "
                    "kept - please try again."
                ),
            )

        # ---------------------------------------
        # Step 6: Send participant invitations
        # ---------------------------------------
        # Best-effort: an email/SMTP failure here must not turn an
        # already-successful scheduling request into a 500 response,
        # since the meeting(s) are already committed at this point.

        if meeting.participant_ids:

            participant_users = (
                UserRepository.get_users_by_ids(
                    db,
                    meeting.participant_ids,
                )
            )

            for participant in participant_users:

                EmailService.try_send_meeting_invitation(
                    to_email=participant.email,
                    meeting_title=meeting.title,
                    start_time=meeting.start_time,
                    end_time=meeting.end_time,
                    location=meeting.location,
                )

        for guest_email in resolved_external_guests:

            EmailService.try_send_meeting_invitation(
                to_email=guest_email,
                meeting_title=meeting.title,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                location=meeting.location,
            )

        # Slack Notifications V1 - independent sibling to the email
        # invitations above, not a modification of them. Sends one
        # owner DM per created occurrence, using each occurrence's own
        # start/end time. Best-effort, never raises.
        for created_meeting_id in created_meetings:
            created_meeting = MeetingRepository.get_by_id(
                db,
                created_meeting_id,
            )
            if created_meeting is not None:
                SlackNotificationService.notify_meeting_created(
                    db,
                    created_meeting,
                )

        if created_meetings:
            cache_delete_prefix(meetings_list_prefix(current_user.id))
            cache_delete(kpis_key(current_user.id))

        return {
            "message": "Meeting(s) scheduled successfully",
            "meeting_ids": created_meetings,
        }

    @staticmethod
    def suggest_slots(
        db: Session,
        meeting: ScheduleMeetingRequest,
        current_user: User,
    ):
        """
        Suggest the first available meeting slot, checking both
        conflicts and declared working-hours availability for the
        owner and every participant. Raises a 404 (rather than
        silently returning None) if no slot is found within the
        search window.
        """

        SchedulerService._validate_participants(db, current_user, meeting)

        suggested_start = meeting.start_time
        suggested_end = meeting.end_time

        for _ in range(MAX_SLOT_ATTEMPTS):

            owner_meetings = (
                MeetingRepository.get_meetings_between(
                    db,
                    current_user.id,
                    suggested_start,
                    suggested_end,
                )
            )

            owner_available = AvailabilityService.is_user_available(
                db,
                current_user.id,
                suggested_start,
                suggested_end,
            )

            if owner_meetings or not owner_available:
                suggested_start += timedelta(hours=1)
                suggested_end += timedelta(hours=1)
                continue

            participant_blocked = False

            for participant_id in meeting.participant_ids:

                participant_meetings = (
                    MeetingRepository.get_meetings_between(
                        db,
                        participant_id,
                        suggested_start,
                        suggested_end,
                    )
                )

                participant_available = (
                    AvailabilityService.is_user_available(
                        db,
                        participant_id,
                        suggested_start,
                        suggested_end,
                    )
                )

                if participant_meetings or not participant_available:
                    participant_blocked = True
                    break

            if participant_blocked:
                suggested_start += timedelta(hours=1)
                suggested_end += timedelta(hours=1)
                continue

            return SuggestSlotsResponse(
                slots=[
                    SuggestedSlot(
                        start_time=suggested_start,
                        end_time=suggested_end,
                    )
                ]
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No available slot found for the owner and all "
                "participants within the searched window."
            ),
        )

    @staticmethod
    def suggest_reschedule_slots(
        db: Session,
        meeting_id: int,
        current_user: User,
        window_days: int = DEFAULT_RESCHEDULE_WINDOW_DAYS,
    ):
        """
        Suggest up to MAX_RESCHEDULE_SUGGESTIONS alternative slots for
        an existing meeting, searching in fixed
        RESCHEDULE_SEARCH_INTERVAL_MINUTES increments across
        `window_days` days starting from the meeting's own
        start_time. The meeting's own duration is preserved for every
        candidate.

        Read-only: this never modifies the meeting, its participants,
        or any external system (Google Calendar/Meet, email) - it
        only returns candidate slots for the caller to act on.
        Raises 404 if no valid slot is found anywhere in the window.
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
                db,
                meeting_id,
                current_user.id,
            )
            is not None
        )

        if not is_owner and not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You must be the meeting owner or a participant "
                    "to request reschedule suggestions."
                ),
            )

        duration = meeting.end_time - meeting.start_time

        participant_ids = [
            participant.user_id
            for participant in (
                MeetingParticipantRepository.get_by_meeting(
                    db,
                    meeting_id,
                )
            )
        ]

        search_end = meeting.start_time + timedelta(days=window_days)
        candidate_start = meeting.start_time
        step = timedelta(minutes=RESCHEDULE_SEARCH_INTERVAL_MINUTES)

        suggestions = []

        while (
            candidate_start + duration <= search_end
            and len(suggestions) < MAX_RESCHEDULE_SUGGESTIONS
        ):
            candidate_end = candidate_start + duration

            owner_meetings = [
                other
                for other in MeetingRepository.get_meetings_between(
                    db,
                    meeting.owner_id,
                    candidate_start,
                    candidate_end,
                )
                if other.id != meeting_id
            ]

            owner_available = AvailabilityService.is_user_available(
                db,
                meeting.owner_id,
                candidate_start,
                candidate_end,
            )

            if owner_meetings or not owner_available:
                candidate_start += step
                continue

            participant_blocked = False

            for participant_id in participant_ids:

                participant_meetings = [
                    other
                    for other in MeetingRepository.get_meetings_between(
                        db,
                        participant_id,
                        candidate_start,
                        candidate_end,
                    )
                    if other.id != meeting_id
                ]

                participant_available = (
                    AvailabilityService.is_user_available(
                        db,
                        participant_id,
                        candidate_start,
                        candidate_end,
                    )
                )

                if participant_meetings or not participant_available:
                    participant_blocked = True
                    break

            if participant_blocked:
                candidate_start += step
                continue

            suggestions.append(
                SuggestedSlot(
                    start_time=candidate_start,
                    end_time=candidate_end,
                )
            )

            candidate_start += step

        if not suggestions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No available reschedule slot found for the "
                    "owner and all participants within the searched "
                    "window."
                ),
            )

        return SuggestSlotsResponse(slots=suggestions)

    @staticmethod
    def update_meeting(
        db: Session,
        meeting_id: int,
        meeting_data: MeetingUpdate,
        current_user: User,
    ):
        db_meeting = MeetingRepository.get_by_id(
            db,
            meeting_id,
        )

        if db_meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found.",
            )

        if db_meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own meetings.",
            )

        update_data = meeting_data.model_dump(
            exclude_unset=True
        )

        for key, value in update_data.items():
            setattr(db_meeting, key, value)

        MeetingRepository.update(
            db,
            db_meeting,
        )

        if db_meeting.google_event_id:
            GoogleCalendarService.update_google_calendar_event(
                db,
                db_meeting,
            )

        # Outlook Calendar sync, parallel to the Google block above.
        # Wrapped in try/except (unlike the Google call above) so an
        # Outlook outage can never block this update.
        if db_meeting.outlook_event_id:
            try:
                OutlookCalendarService.update_outlook_calendar_event(
                    db,
                    db_meeting,
                )
            except Exception:
                logger.exception(
                    "Outlook Calendar integration failed during "
                    "meeting update. meeting_id=%s",
                    db_meeting.id,
                )

        # Microsoft Teams sync, parallel to the Outlook block above -
        # only re-asserted when this meeting already has Teams
        # enabled, and only possible while its Outlook event exists.
        if db_meeting.teams_join_url and db_meeting.outlook_event_id:
            try:
                teams_event = TeamsMeetingService.enable_teams_meeting(
                    db=db,
                    user_id=db_meeting.owner_id,
                    event_id=db_meeting.outlook_event_id,
                )

                joined_url = (
                    teams_event.get("onlineMeeting") or {}
                ).get("joinUrl")
                if joined_url:
                    db_meeting.teams_join_url = joined_url
                    db_meeting = MeetingRepository.update(db, db_meeting)
            except Exception:
                logger.exception(
                    "Microsoft Teams integration failed during "
                    "meeting update. meeting_id=%s",
                    db_meeting.id,
                )

        # Zoom Meeting sync, parallel to the Google/Outlook/Teams
        # blocks above.
        if db_meeting.zoom_meeting_id:
            try:
                ZoomCalendarService.update_zoom_meeting(
                    db,
                    db_meeting,
                )
            except Exception:
                logger.exception(
                    "Zoom Meeting integration failed during meeting "
                    "update. meeting_id=%s",
                    db_meeting.id,
                )

        # Best-effort: the update is already committed above.
        MeetingNotificationService.notify_meeting_updated(db, db_meeting)

        # Slack Notifications V1 - independent sibling to the email
        # notification above. Best-effort, never raises.
        SlackNotificationService.notify_meeting_updated(db, db_meeting)

        cache_delete_prefix(meetings_list_prefix(db_meeting.owner_id))

        return db_meeting

    @staticmethod
    def _find_auto_reschedule_slot(
        db: Session,
        meeting: Meeting,
        participant_ids: list[int],
        window_days: int,
    ):
        """
        Finds the first candidate slot, strictly after the meeting's
        current start_time, that preserves its duration and is free
        for the owner, every participant, and (if assigned) the
        meeting's resource - checking both existing-meeting conflicts
        and declared working-hours availability. Mirrors the search
        pattern already used by suggest_reschedule_slots, with an
        added resource-conflict check (auto-reschedule must not
        double-book a resource, unlike the read-only suggestion
        endpoint). Returns None if the window is exhausted.
        """
        duration = meeting.end_time - meeting.start_time
        search_end = meeting.start_time + timedelta(days=window_days)
        step = timedelta(minutes=RESCHEDULE_SEARCH_INTERVAL_MINUTES)
        candidate_start = meeting.start_time + step

        while candidate_start + duration <= search_end:
            candidate_end = candidate_start + duration

            owner_meetings = [
                other
                for other in MeetingRepository.get_meetings_between(
                    db,
                    meeting.owner_id,
                    candidate_start,
                    candidate_end,
                )
                if other.id != meeting.id
            ]

            owner_available = AvailabilityService.is_user_available(
                db,
                meeting.owner_id,
                candidate_start,
                candidate_end,
            )

            if owner_meetings or not owner_available:
                candidate_start += step
                continue

            participant_blocked = False

            for participant_id in participant_ids:

                participant_meetings = [
                    other
                    for other in MeetingRepository.get_meetings_between(
                        db,
                        participant_id,
                        candidate_start,
                        candidate_end,
                    )
                    if other.id != meeting.id
                ]

                participant_available = (
                    AvailabilityService.is_user_available(
                        db,
                        participant_id,
                        candidate_start,
                        candidate_end,
                    )
                )

                if participant_meetings or not participant_available:
                    participant_blocked = True
                    break

            if participant_blocked:
                candidate_start += step
                continue

            if meeting.resource_id is not None:
                resource_bookings = [
                    other
                    for other in (
                        MeetingRepository.get_resource_bookings_between(
                            db,
                            meeting.resource_id,
                            candidate_start,
                            candidate_end,
                        )
                    )
                    if other.id != meeting.id
                ]

                if resource_bookings:
                    candidate_start += step
                    continue

            return SuggestedSlot(
                start_time=candidate_start,
                end_time=candidate_end,
            )

        return None

    @staticmethod
    def auto_reschedule_meeting(
        db: Session,
        meeting_id: int,
        current_user: User,
        window_days: int = DEFAULT_RESCHEDULE_WINDOW_DAYS,
    ) -> AutoRescheduleResponse:
        """
        Automatically moves an existing meeting to the first open
        slot within `window_days`, preserving its duration,
        participants, external guests, and resource assignment. Only
        the meeting owner may trigger this (mirrors the owner-only
        rule already enforced by MeetingService.update_meeting).

        Persists the change through MeetingService.update_meeting -
        the same path used by a manual PUT /meetings/{id} edit - so
        this gets identical Google Calendar sync, notification, and
        cache-invalidation behavior with no duplicated logic.

        Recurring meetings are not specially handled: this schema has
        no series concept at all (a "recurring" meeting is just N
        independent Meeting rows), so operating on a single
        meeting_id can only ever move that one row, never a series.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found.",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can auto-reschedule it.",
            )

        previous_start_time = meeting.start_time
        previous_end_time = meeting.end_time

        participant_ids = [
            participant.user_id
            for participant in MeetingParticipantRepository.get_by_meeting(
                db,
                meeting_id,
            )
        ]

        new_slot = SchedulerService._find_auto_reschedule_slot(
            db,
            meeting,
            participant_ids,
            window_days,
        )

        if new_slot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No available slot was found for the owner, "
                    "participants, and resource within the next "
                    f"{window_days} day(s). The meeting was not "
                    "changed."
                ),
            )

        updated_meeting = MeetingService.update_meeting(
            db,
            meeting_id,
            MeetingUpdate(
                start_time=new_slot.start_time,
                end_time=new_slot.end_time,
            ),
            current_user,
        )

        return AutoRescheduleResponse(
            meeting=updated_meeting,
            previous_start_time=previous_start_time,
            previous_end_time=previous_end_time,
            new_start_time=new_slot.start_time,
            new_end_time=new_slot.end_time,
            message=(
                f"Meeting moved from "
                f"{previous_start_time.isoformat()} to "
                f"{new_slot.start_time.isoformat()}."
            ),
        )
