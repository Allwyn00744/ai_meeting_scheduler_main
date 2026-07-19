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
    def notify_meeting_created(db: Session, meeting: Meeting) -> None:
        for email in MeetingNotificationService._resolve_recipients(
            db,
            meeting,
        ):
            EmailService.try_send_meeting_invitation(
                to_email=email,
                meeting_title=meeting.title,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                location=meeting.location,
            )

    @staticmethod
    def notify_meeting_updated(db: Session, meeting: Meeting) -> None:
        for email in MeetingNotificationService._resolve_recipients(
            db,
            meeting,
        ):
            EmailService.try_send_meeting_update(
                to_email=email,
                meeting_title=meeting.title,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                location=meeting.location,
            )

    @staticmethod
    def notify_meeting_cancelled(db: Session, meeting: Meeting) -> None:
        for email in MeetingNotificationService._resolve_recipients(
            db,
            meeting,
        ):
            EmailService.try_send_meeting_cancellation(
                to_email=email,
                meeting_title=meeting.title,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
            )
