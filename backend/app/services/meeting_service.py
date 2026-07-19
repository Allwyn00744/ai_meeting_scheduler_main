import logging

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import date

from app.core.cache import (
    MEETINGS_LIST_TTL_SECONDS,
    cache_delete,
    cache_get,
    cache_set,
    cache_delete_prefix,
    kpis_key,
    meetings_list_key,
    meetings_list_prefix,
)
from app.models.external_meeting_guest import ExternalMeetingGuest
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories.external_meeting_guest_repository import (
    ExternalMeetingGuestRepository,
)
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.resource_repository import ResourceRepository
from app.schemas.meeting import MeetingCreate, MeetingResponse, MeetingUpdate
from app.services.analytics_service import (
    EVENT_CONFLICT_BLOCKED_OWNER,
    EVENT_CONFLICT_BLOCKED_RESOURCE,
    AnalyticsService,
)
from app.services.conflict_service import ConflictService
from app.services.external_guest_service import ExternalGuestService
from app.services.google_calendar_service import GoogleCalendarService
from app.services.meeting_notification_service import (
    MeetingNotificationService,
)
from app.services.outlook_calendar_service import OutlookCalendarService
from app.services.push_notification_service import PushNotificationService
from app.services.slack_notification_service import SlackNotificationService
from app.services.teams_meeting_service import TeamsMeetingService
from app.services.whatsapp_notification_service import (
    WhatsAppNotificationService,
)
from app.services.zoom_calendar_service import ZoomCalendarService

logger = logging.getLogger(__name__)


class MeetingService:

    @staticmethod
    def create_meeting(
        db: Session,
        meeting: MeetingCreate,
        current_user: User,
    ):
        # Get all meetings of the current user
        existing_meetings = MeetingRepository.get_user_meetings(
            db,
            current_user.id,
        )

        # Check for conflicts
        conflict, existing_meeting = ConflictService.has_time_conflict(
            meeting.start_time,
            meeting.end_time,
            existing_meetings,
        )

        if conflict:
            AnalyticsService.try_record_event(
                current_user.id,
                EVENT_CONFLICT_BLOCKED_OWNER,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Meeting conflicts with "
                    f"'{existing_meeting.title}'"
                ),
            )

        # Resource booking is optional. When requested, the resource
        # must exist, be active, and be free for this time range -
        # validated before the meeting is created.
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

            resource_conflict, conflicting_meeting = (
                ConflictService.check_resource_conflict(
                    db,
                    meeting.resource_id,
                    meeting.start_time,
                    meeting.end_time,
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
                        f"Resource '{resource.name}' is already "
                        f"booked for '{conflicting_meeting.title}'."
                    ),
                )

        # Resolve external guests before writing anything. This path
        # has no participant_ids, so only the owner-collision rule
        # applies (participant_emails is empty).
        resolved_guests = ExternalGuestService.resolve_guests(
            meeting.external_guest_emails,
            current_user.email,
            [],
        )

        # Create the meeting
        db_meeting = Meeting(
            title=meeting.title,
            description=meeting.description,
            start_time=meeting.start_time,
            end_time=meeting.end_time,
            location=meeting.location,
            owner_id=current_user.id,
            resource_id=meeting.resource_id,
        )

        db_meeting = MeetingRepository.create(db, db_meeting)

        if resolved_guests:
            ExternalMeetingGuestRepository.create_many(
                db,
                [
                    ExternalMeetingGuest(
                        meeting_id=db_meeting.id,
                        email=email,
                    )
                    for email in resolved_guests
                ],
            )

        # Google Calendar sync is a best-effort side effect, isolated
        # from the database transaction above (already committed):
        # PostgreSQL and Google Calendar are two separate systems with
        # no distributed transaction between them. Mirrors the same
        # pattern used by SchedulerService.schedule_meeting so this
        # endpoint's meetings also show up on the owner's calendar.
        try:
            event = GoogleCalendarService.create_google_calendar_event(
                db=db,
                user_id=current_user.id,
                title=db_meeting.title,
                description=db_meeting.description or "",
                start_time=db_meeting.start_time,
                end_time=db_meeting.end_time,
                location=db_meeting.location,
                attendee_emails=resolved_guests,
            )

            db_meeting.google_event_id = event.get("id")
            db_meeting.google_event_link = event.get("htmlLink")
            db_meeting.google_meet_link = event.get("hangoutLink")

            db.commit()
            db.refresh(db_meeting)
        except Exception:
            logger.exception(
                "Google Calendar integration failed. meeting_id=%s",
                db_meeting.id,
            )

        # Outlook Calendar sync is a second, independent best-effort
        # side effect, parallel to the Google block above - each
        # provider is optional and connecting one must never affect
        # the other. Gated on is_outlook_connected() first so the
        # common "Outlook not connected" case skips straight past
        # without paying for a credential fetch + exception.
        if OutlookCalendarService.is_outlook_connected(
            db,
            current_user.id,
        ):
            try:
                outlook_event = (
                    OutlookCalendarService.create_outlook_calendar_event(
                        db=db,
                        user_id=current_user.id,
                        title=db_meeting.title,
                        description=db_meeting.description or "",
                        start_time=db_meeting.start_time,
                        end_time=db_meeting.end_time,
                        location=db_meeting.location,
                        attendee_emails=resolved_guests,
                    )
                )

                db_meeting.outlook_event_id = outlook_event.get("id")
                db_meeting.outlook_event_link = outlook_event.get(
                    "webLink"
                )

                db.commit()
                db.refresh(db_meeting)
            except Exception:
                logger.exception(
                    "Outlook Calendar integration failed. "
                    "meeting_id=%s",
                    db_meeting.id,
                )

        # Microsoft Teams sync is a third, independent best-effort side
        # effect - but unlike Google/Outlook/Zoom it never creates its
        # own resource. It only extends the Outlook event just created
        # above (isOnlineMeeting/onlineMeetingProvider), so it only
        # runs when that Outlook block succeeded in this same request.
        if db_meeting.outlook_event_id:
            try:
                teams_event = TeamsMeetingService.enable_teams_meeting(
                    db=db,
                    user_id=current_user.id,
                    event_id=db_meeting.outlook_event_id,
                )

                db_meeting.teams_join_url = (
                    teams_event.get("onlineMeeting") or {}
                ).get("joinUrl")

                db.commit()
                db.refresh(db_meeting)
            except Exception:
                logger.exception(
                    "Microsoft Teams integration failed. meeting_id=%s",
                    db_meeting.id,
                )

        # Zoom Meeting sync is a fourth, independent best-effort side
        # effect, parallel to the Google, Outlook, and Teams blocks
        # above - each provider is optional and connecting one must
        # never affect the others.
        if ZoomCalendarService.is_zoom_connected(
            db,
            current_user.id,
        ):
            try:
                zoom_meeting = ZoomCalendarService.create_zoom_meeting(
                    db=db,
                    user_id=current_user.id,
                    title=db_meeting.title,
                    description=db_meeting.description or "",
                    start_time=db_meeting.start_time,
                    end_time=db_meeting.end_time,
                )

                db_meeting.zoom_meeting_id = str(zoom_meeting.get("id"))
                db_meeting.zoom_join_url = zoom_meeting.get("join_url")
                db_meeting.zoom_start_url = zoom_meeting.get("start_url")

                db.commit()
                db.refresh(db_meeting)
            except Exception:
                logger.exception(
                    "Zoom Meeting integration failed. meeting_id=%s",
                    db_meeting.id,
                )

        # Best-effort: the meeting is already committed above, so an
        # SMTP failure here must not turn a successful creation into
        # a failed request.
        MeetingNotificationService.notify_meeting_created(db, db_meeting)

        # Slack Notifications V1 - an independent sibling to the email
        # notification above, not a modification of it. A Slack outage
        # or a meeting owner who never connected Slack must never
        # affect email delivery, and vice versa. Best-effort, never
        # raises.
        SlackNotificationService.notify_meeting_created(db, db_meeting)

        # WhatsApp Notifications V1 - independent sibling to the email
        # and Slack notifications above. Best-effort, never raises.
        WhatsAppNotificationService.notify_meeting_created(db, db_meeting)

        # Push Notifications V1 - independent sibling to the email,
        # Slack, and WhatsApp notifications above. Best-effort, never
        # raises.
        PushNotificationService.notify_meeting_created(db, db_meeting)

        # The meeting is already committed above; cache invalidation
        # is best-effort and must not affect the response either way.
        cache_delete_prefix(meetings_list_prefix(current_user.id))
        cache_delete(kpis_key(current_user.id))

        return db_meeting

    @staticmethod
    def get_meeting_by_id(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        is_owner = meeting.owner_id == current_user.id

        is_participant = MeetingParticipantRepository.get_by_meeting_and_user(
            db,
            meeting_id,
            current_user.id,
        ) is not None

        if not is_owner and not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You must be the meeting owner or a participant "
                    "to view this meeting."
                ),
            )

        # zoom_start_url is the Zoom host key for this meeting (start
        # controls, e.g. muting participants) - only the meeting owner
        # may see it. Cleared on the in-memory object only (no commit
        # follows), so this never persists to the database.
        if not is_owner:
            meeting.zoom_start_url = None

        return meeting

    @staticmethod
    def get_my_meetings(
        db: Session,
        current_user: User,
        limit: int | None = None,
        offset: int = 0,
    ):
        cache_key = meetings_list_key(current_user.id, limit, offset)
        cached = cache_get(cache_key)

        if cached is not None:
            return cached

        meetings = MeetingRepository.get_all(
            db,
            current_user.id,
            limit=limit,
            offset=offset,
        )

        serialized = [
            MeetingResponse.model_validate(meeting).model_dump(
                mode="json"
            )
            for meeting in meetings
        ]

        if serialized:
            cache_set(cache_key, serialized, MEETINGS_LIST_TTL_SECONDS)

        return serialized

    @staticmethod
    def update_meeting(
        db: Session,
        meeting_id: int,
        meeting_data: MeetingUpdate,
        current_user: User,
    ):
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        update_data = meeting_data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(meeting, key, value)

        meeting = MeetingRepository.update(db, meeting)

        # Google Calendar sync is a best-effort side effect, isolated
        # from the database transaction above (already committed): a
        # Calendar failure must not turn an already-persisted update
        # into a failed response, mirroring the pattern used by
        # create_meeting.
        if meeting.google_event_id:
            try:
                GoogleCalendarService.update_google_calendar_event(
                    db=db,
                    meeting=meeting,
                )
            except Exception:
                logger.exception(
                    "Google Calendar integration failed during "
                    "meeting update. meeting_id=%s",
                    meeting.id,
                )

        # Outlook Calendar sync, parallel to the Google block above.
        if meeting.outlook_event_id:
            try:
                OutlookCalendarService.update_outlook_calendar_event(
                    db=db,
                    meeting=meeting,
                )
            except Exception:
                logger.exception(
                    "Outlook Calendar integration failed during "
                    "meeting update. meeting_id=%s",
                    meeting.id,
                )

        # Microsoft Teams sync, parallel to the Outlook block above -
        # only re-asserted when this meeting already has Teams enabled
        # (there is nothing to update otherwise), and only possible
        # while the Outlook event it extends still exists.
        if meeting.teams_join_url and meeting.outlook_event_id:
            try:
                teams_event = TeamsMeetingService.enable_teams_meeting(
                    db=db,
                    user_id=current_user.id,
                    event_id=meeting.outlook_event_id,
                )

                joined_url = (
                    teams_event.get("onlineMeeting") or {}
                ).get("joinUrl")
                if joined_url:
                    meeting.teams_join_url = joined_url
                    meeting = MeetingRepository.update(db, meeting)
            except Exception:
                logger.exception(
                    "Microsoft Teams integration failed during "
                    "meeting update. meeting_id=%s",
                    meeting.id,
                )

        # Zoom Meeting sync, parallel to the Google/Outlook/Teams
        # blocks above.
        if meeting.zoom_meeting_id:
            try:
                ZoomCalendarService.update_zoom_meeting(
                    db=db,
                    meeting=meeting,
                )
            except Exception:
                logger.exception(
                    "Zoom Meeting integration failed during meeting "
                    "update. meeting_id=%s",
                    meeting.id,
                )

        # Best-effort: the update is already committed above.
        MeetingNotificationService.notify_meeting_updated(db, meeting)

        # Slack Notifications V1 - independent sibling to the email
        # notification above. Best-effort, never raises.
        SlackNotificationService.notify_meeting_updated(db, meeting)

        # WhatsApp Notifications V1 - independent sibling to the email
        # and Slack notifications above. Best-effort, never raises.
        WhatsAppNotificationService.notify_meeting_updated(db, meeting)

        # Push Notifications V1 - independent sibling to the email,
        # Slack, and WhatsApp notifications above. Best-effort, never
        # raises.
        PushNotificationService.notify_meeting_updated(db, meeting)

        cache_delete_prefix(meetings_list_prefix(current_user.id))

        return meeting

    @staticmethod
    def delete_meeting(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        meeting = MeetingRepository.get_by_id(
            db,
            meeting_id,
        )

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        # Delete Google Calendar event first. Note: this is a
        # best-effort side effect, not part of the same atomic
        # transaction as the database delete below - Google Calendar
        # and PostgreSQL are two separate systems with no distributed
        # transaction between them.
        if meeting.google_event_id:
            GoogleCalendarService.delete_google_calendar_event(
                db=db,
                meeting=meeting,
            )

        # Outlook Calendar sync, parallel to the Google block above.
        # Wrapped in try/except (unlike the Google call above) so an
        # Outlook outage can never block a meeting deletion. No
        # separate Microsoft Teams deletion call is needed here: a
        # Teams meeting isn't its own resource, it's this same Outlook
        # event with isOnlineMeeting/onlineMeetingProvider set, so
        # deleting the event below removes the Teams meeting on
        # Microsoft's side too.
        if meeting.outlook_event_id:
            try:
                OutlookCalendarService.delete_outlook_calendar_event(
                    db=db,
                    meeting=meeting,
                )
            except Exception:
                logger.exception(
                    "Outlook Calendar integration failed during "
                    "meeting delete. meeting_id=%s",
                    meeting.id,
                )

        # Zoom Meeting sync, parallel to the Google/Outlook blocks
        # above. Wrapped so a Zoom outage can never block a meeting
        # deletion.
        if meeting.zoom_meeting_id:
            try:
                ZoomCalendarService.delete_zoom_meeting(
                    db=db,
                    meeting=meeting,
                )
            except Exception:
                logger.exception(
                    "Zoom Meeting integration failed during meeting "
                    "delete. meeting_id=%s",
                    meeting.id,
                )

        # Resolve recipients and notify before the delete below -
        # participant/external-guest rows are removed via ON DELETE
        # CASCADE once the meeting row is gone, so they must be read
        # first. Best-effort: an SMTP failure must not block deletion.
        MeetingNotificationService.notify_meeting_cancelled(db, meeting)

        # Slack Notifications V1 - independent sibling to the email
        # notification above. Best-effort, never raises, and must not
        # block deletion either.
        SlackNotificationService.notify_meeting_cancelled(db, meeting)

        # WhatsApp Notifications V1 - independent sibling to the email
        # and Slack notifications above. Best-effort, never raises,
        # and must not block deletion either.
        WhatsAppNotificationService.notify_meeting_cancelled(db, meeting)

        # Push Notifications V1 - independent sibling to the email,
        # Slack, and WhatsApp notifications above. Best-effort, never
        # raises, and must not block deletion either.
        PushNotificationService.notify_meeting_cancelled(db, meeting)

        # Delete meeting from database. Participant rows are removed
        # automatically at the database level (ON DELETE CASCADE on
        # meeting_participants.meeting_id), so no manual participant
        # cleanup is needed here.
        try:
            MeetingRepository.delete(
                db,
                meeting,
            )
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Unable to delete meeting due to related "
                    "records. Please try again or contact support."
                ),
            )

        cache_delete_prefix(meetings_list_prefix(current_user.id))
        cache_delete(kpis_key(current_user.id))

        return {
            "message": "Meeting deleted successfully"
        }

    @staticmethod
    def create_outlook_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by POST /outlook/sync/{meeting_id}. Manually creates the
        Outlook event for a meeting that was created before Outlook
        was connected, or to retry a failed automatic sync - the
        automatic path lives in create_meeting above.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if meeting.outlook_event_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Meeting is already synced to Outlook Calendar. "
                    "Use PUT to update it instead."
                ),
            )

        event = OutlookCalendarService.create_outlook_calendar_event(
            db=db,
            user_id=current_user.id,
            title=meeting.title,
            description=meeting.description or "",
            start_time=meeting.start_time,
            end_time=meeting.end_time,
            location=meeting.location,
            attendee_emails=[
                guest.email for guest in meeting.external_guests
            ],
        )

        meeting.outlook_event_id = event.get("id")
        meeting.outlook_event_link = event.get("webLink")

        meeting = MeetingRepository.update(db, meeting)

        return {
            "message": "Meeting synced to Outlook Calendar successfully",
            "outlook_event_id": meeting.outlook_event_id,
            "outlook_event_link": meeting.outlook_event_link,
        }

    @staticmethod
    def update_outlook_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by PUT /outlook/sync/{meeting_id}. Manually re-pushes the
        current meeting data to its existing Outlook event - a retry
        tool for when the automatic sync in update_meeting above
        failed.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if not meeting.outlook_event_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Meeting is not synced to Outlook Calendar yet. "
                    "Use POST to sync it first."
                ),
            )

        event = OutlookCalendarService.update_outlook_calendar_event(
            db=db,
            meeting=meeting,
        )

        if event.get("webLink"):
            meeting.outlook_event_link = event.get("webLink")
            meeting = MeetingRepository.update(db, meeting)

        return {
            "message": "Outlook Calendar event updated successfully",
            "outlook_event_id": meeting.outlook_event_id,
            "outlook_event_link": meeting.outlook_event_link,
        }

    @staticmethod
    def delete_outlook_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by DELETE /outlook/sync/{meeting_id}. Unlinks this one
        meeting from Outlook Calendar (deletes the Outlook event and
        clears outlook_event_id/link) without deleting the Meeting
        itself.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if not meeting.outlook_event_id:
            return {
                "message": "Meeting was not synced to Outlook Calendar",
            }

        OutlookCalendarService.delete_outlook_calendar_event(
            db=db,
            meeting=meeting,
        )

        meeting.outlook_event_id = None
        meeting.outlook_event_link = None
        MeetingRepository.update(db, meeting)

        return {
            "message": "Outlook Calendar event unlinked successfully",
        }

    @staticmethod
    def create_teams_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by POST /teams/sync/{meeting_id}. Turns this meeting's
        existing Outlook event into a Teams meeting - it does not
        create an Outlook event itself, since Teams Integration V1
        extends the Outlook event rather than being a standalone
        resource. Sync to Outlook first (POST /outlook/sync) if the
        meeting has no outlook_event_id yet.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if meeting.teams_join_url:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Meeting is already synced to Microsoft Teams. "
                    "Use PUT to update it instead."
                ),
            )

        if not meeting.outlook_event_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Meeting must be synced to Outlook Calendar first. "
                    "Use POST /outlook/sync, then try again."
                ),
            )

        event = TeamsMeetingService.enable_teams_meeting(
            db=db,
            user_id=current_user.id,
            event_id=meeting.outlook_event_id,
        )

        meeting.teams_join_url = (
            event.get("onlineMeeting") or {}
        ).get("joinUrl")

        meeting = MeetingRepository.update(db, meeting)

        return {
            "message": "Meeting synced to Microsoft Teams successfully",
            "teams_join_url": meeting.teams_join_url,
        }

    @staticmethod
    def update_teams_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by PUT /teams/sync/{meeting_id}. Re-asserts Teams on the
        meeting's existing Outlook event - a retry tool for when the
        automatic sync in update_meeting above failed, or to refresh
        the stored join URL.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if not meeting.teams_join_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Meeting is not synced to Microsoft Teams yet. "
                    "Use POST to sync it first."
                ),
            )

        if not meeting.outlook_event_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Meeting's Outlook event no longer exists. Sync "
                    "to Outlook again, then re-sync to Teams."
                ),
            )

        event = TeamsMeetingService.enable_teams_meeting(
            db=db,
            user_id=current_user.id,
            event_id=meeting.outlook_event_id,
        )

        joined_url = (event.get("onlineMeeting") or {}).get("joinUrl")
        if joined_url:
            meeting.teams_join_url = joined_url
            meeting = MeetingRepository.update(db, meeting)

        return {
            "message": "Microsoft Teams meeting updated successfully",
            "teams_join_url": meeting.teams_join_url,
        }

    @staticmethod
    def delete_teams_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by DELETE /teams/sync/{meeting_id}. Unlinks this one
        meeting from Microsoft Teams (turns Teams off on its Outlook
        event and clears teams_join_url) without deleting the Outlook
        event or the Meeting itself.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if not meeting.teams_join_url:
            return {
                "message": "Meeting was not synced to Microsoft Teams",
            }

        TeamsMeetingService.disable_teams_meeting(
            db=db,
            meeting=meeting,
        )

        meeting.teams_join_url = None
        MeetingRepository.update(db, meeting)

        return {
            "message": "Microsoft Teams meeting unlinked successfully",
        }

    @staticmethod
    def create_zoom_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by POST /zoom/sync/{meeting_id}. Manually creates the
        Zoom meeting for a meeting that was created before Zoom was
        connected, or to retry a failed automatic sync - the automatic
        path lives in create_meeting above.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if meeting.zoom_meeting_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Meeting is already synced to Zoom. Use PUT to "
                    "update it instead."
                ),
            )

        zoom_meeting = ZoomCalendarService.create_zoom_meeting(
            db=db,
            user_id=current_user.id,
            title=meeting.title,
            description=meeting.description or "",
            start_time=meeting.start_time,
            end_time=meeting.end_time,
        )

        meeting.zoom_meeting_id = str(zoom_meeting.get("id"))
        meeting.zoom_join_url = zoom_meeting.get("join_url")
        meeting.zoom_start_url = zoom_meeting.get("start_url")

        meeting = MeetingRepository.update(db, meeting)

        return {
            "message": "Meeting synced to Zoom successfully",
            "zoom_meeting_id": meeting.zoom_meeting_id,
            "zoom_join_url": meeting.zoom_join_url,
            "zoom_start_url": meeting.zoom_start_url,
        }

    @staticmethod
    def update_zoom_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by PUT /zoom/sync/{meeting_id}. Manually re-pushes the
        current meeting data to its existing Zoom meeting - a retry
        tool for when the automatic sync in update_meeting above
        failed.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if not meeting.zoom_meeting_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Meeting is not synced to Zoom yet. Use POST to "
                    "sync it first."
                ),
            )

        ZoomCalendarService.update_zoom_meeting(
            db=db,
            meeting=meeting,
        )

        return {
            "message": "Zoom meeting updated successfully",
            "zoom_meeting_id": meeting.zoom_meeting_id,
            "zoom_join_url": meeting.zoom_join_url,
            "zoom_start_url": meeting.zoom_start_url,
        }

    @staticmethod
    def delete_zoom_sync(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by DELETE /zoom/sync/{meeting_id}. Unlinks this one
        meeting from Zoom (deletes the Zoom meeting and clears
        zoom_meeting_id/join_url/start_url) without deleting the
        Meeting itself.
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if not meeting.zoom_meeting_id:
            return {
                "message": "Meeting was not synced to Zoom",
            }

        ZoomCalendarService.delete_zoom_meeting(
            db=db,
            meeting=meeting,
        )

        meeting.zoom_meeting_id = None
        meeting.zoom_join_url = None
        meeting.zoom_start_url = None
        MeetingRepository.update(db, meeting)

        return {
            "message": "Zoom meeting unlinked successfully",
        }

    @staticmethod
    def send_slack_notification(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        """
        Used by POST /slack/send/{meeting_id}. Manually (re)sends a
        Slack direct-message notification for this meeting to its
        owner - for a meeting created before Slack was connected, or
        to retry a failed automatic notification. Sends the same
        notification content as the automatic create/update/cancel
        notifications (see
        SlackNotificationService.send_manual_notification).
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        SlackNotificationService.send_manual_notification(db, meeting)

        return {
            "message": "Slack notification sent successfully",
        }

    @staticmethod
    def send_whatsapp_notification(
        db: Session,
        meeting_id: int,
        current_user: User,
        message: str | None = None,
    ):
        """
        Used by POST /whatsapp/send/{meeting_id}. Manually (re)sends a
        WhatsApp notification for this meeting to its owner - for a
        meeting created before WhatsApp was enabled, or to retry a
        failed automatic notification. Mirrors
        MeetingService.send_slack_notification above (see
        WhatsAppNotificationService.send_manual_notification).
        """
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        WhatsAppNotificationService.send_manual_notification(
            db,
            meeting,
            message,
        )

        return {
            "message": "WhatsApp notification sent successfully",
        }

    @staticmethod
    def search_meetings(
        db: Session,
        keyword: str,
        current_user: User,
        limit: int | None = None,
        offset: int = 0,
    ):
        return MeetingRepository.search_meetings(
            db,
            current_user.id,
            keyword,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def filter_by_status(
        db: Session,
        status: str,
        current_user: User,
        limit: int | None = None,
        offset: int = 0,
    ):
        return MeetingRepository.filter_by_status(
            db,
            current_user.id,
            status,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def filter_by_date(
        db: Session,
        meeting_date: date,
        current_user: User,
        limit: int | None = None,
        offset: int = 0,
    ):
        return MeetingRepository.filter_by_date(
            db,
            current_user.id,
            meeting_date,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def filter_by_date_range(
        db: Session,
        start_date: date,
        end_date: date,
        current_user: User,
        limit: int | None = None,
        offset: int = 0,
    ):
        return MeetingRepository.filter_by_date_range(
            db,
            current_user.id,
            start_date,
            end_date,
            limit=limit,
            offset=offset,
        )
