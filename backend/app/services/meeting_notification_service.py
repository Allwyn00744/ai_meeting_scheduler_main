from sqlalchemy.orm import Session

from app.models.meeting import Meeting
from app.repositories.external_meeting_guest_repository import (
    ExternalMeetingGuestRepository,
)
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.user_repository import UserRepository
from app.services.email_service import EmailService
from app.services.notification_log_service import NotificationLogService


class MeetingNotificationService:
    """
    Centralizes recipient resolution for meeting update/cancellation
    notifications (internal participants + external guests, deduped),
    so call sites (MeetingService, SchedulerService) don't each
    re-implement it. Actual delivery is always delegated to
    EmailService - this class never talks to SMTP directly.
    """

    @staticmethod
    def _resolve_recipients(db: Session, meeting: Meeting) -> list[str]:
        participant_rows = MeetingParticipantRepository.get_by_meeting(
            db,
            meeting.id,
        )

        participant_user_ids = [row.user_id for row in participant_rows]

        participant_users = (
            UserRepository.get_users_by_ids(db, participant_user_ids)
            if participant_user_ids
            else []
        )

        guest_rows = ExternalMeetingGuestRepository.get_by_meeting(
            db,
            meeting.id,
        )

        candidate_emails = [user.email for user in participant_users] + [
            guest.email for guest in guest_rows
        ]

        deduped: list[str] = []
        seen: set[str] = set()

        for email in candidate_emails:
            normalized = email.strip().lower()

            if normalized in seen:
                continue

            seen.add(normalized)
            deduped.append(normalized)

        return deduped

    @staticmethod
    def _resolve_created_recipients(
        db: Session,
        meeting: Meeting,
    ) -> list[str]:
        """
        Like _resolve_recipients, but also includes the meeting owner -
        unlike an update/cancellation (where the owner is the one who
        made the change and already knows about it), the owner has no
        other way to get a confirmation that their own meeting was
        created, since MeetingCreate has no participant_ids field and
        participants are only ever added afterward via a separate
        endpoint.
        """
        recipients = MeetingNotificationService._resolve_recipients(
            db,
            meeting,
        )

        owner = UserRepository.get_user_by_id(db, meeting.owner_id)

        if owner is not None and owner.email:
            normalized_owner_email = owner.email.strip().lower()

            if normalized_owner_email not in recipients:
                recipients = [normalized_owner_email] + recipients

        return recipients

    @staticmethod
    def notify_meeting_created(db: Session, meeting: Meeting) -> None:
        for email in MeetingNotificationService._resolve_created_recipients(
            db,
            meeting,
        ):
            sent = EmailService.try_send_meeting_invitation(
                to_email=email,
                meeting_title=meeting.title,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                location=meeting.location,
            )
            NotificationLogService.try_record(
                user_id=meeting.owner_id,
                channel="email",
                event_type="created",
                success=sent,
                meeting_id=meeting.id,
            )

    @staticmethod
    def notify_meeting_updated(db: Session, meeting: Meeting) -> None:
        for email in MeetingNotificationService._resolve_recipients(
            db,
            meeting,
        ):
            sent = EmailService.try_send_meeting_update(
                to_email=email,
                meeting_title=meeting.title,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                location=meeting.location,
            )
            NotificationLogService.try_record(
                user_id=meeting.owner_id,
                channel="email",
                event_type="updated",
                success=sent,
                meeting_id=meeting.id,
            )

    @staticmethod
    def notify_meeting_cancelled(db: Session, meeting: Meeting) -> None:
        for email in MeetingNotificationService._resolve_recipients(
            db,
            meeting,
        ):
            sent = EmailService.try_send_meeting_cancellation(
                to_email=email,
                meeting_title=meeting.title,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
            )
            NotificationLogService.try_record(
                user_id=meeting.owner_id,
                channel="email",
                event_type="cancelled",
                success=sent,
                meeting_id=meeting.id,
            )
