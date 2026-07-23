import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.integrations.slack_client import SlackAPI
from app.models.meeting import Meeting
from app.models.slack_credential import SlackCredential
from app.repositories.slack_credential_repository import (
    SlackCredentialRepository,
)

logger = logging.getLogger(__name__)


class SlackNotificationService:
    """
    Slack Notifications V1. Deliberately independent of
    MeetingNotificationService (email) - a Slack outage or
    misconfiguration must never affect email delivery, Google/Outlook/
    Teams/Zoom sync, or Meeting Intelligence, and vice versa. Notifies
    only the meeting owner (the Slack user who completed OAuth) via
    direct message - there is no participant/external-guest fan-out
    like the email path, since only the owner has a Slack identity on
    file in V1, and there is no channel-selection concept either.
    """

    @staticmethod
    def is_slack_connected(db: Session, user_id: int) -> bool:
        """
        Cheap, read-only check for whether this user has a stored
        Slack credential - does not call the Slack API. Callers that
        want to skip Slack entirely can use this instead of paying for
        a fetch + send attempt.
        """
        return (
            SlackCredentialRepository.get_by_user_id(db, user_id)
            is not None
        )

    @staticmethod
    def get_connection_status(db: Session, user_id: int) -> dict:
        """
        Used by GET /slack/status. Returns whether this user has a
        stored Slack credential (a cheap, read-only check for the
        Settings UI to render Connected/Not connected).
        """
        return {
            "connected": SlackNotificationService.is_slack_connected(
                db,
                user_id,
            ),
        }

    @staticmethod
    def save_slack_credentials(
        db: Session,
        user_id: int,
        token_response: dict,
    ) -> SlackCredential:
        """
        Persists (or refreshes) the Slack credential for user_id from a
        successful oauth.v2.access response. Slack bot tokens obtained
        this way do not expire by default (no token rotation opted
        into), so unlike ZoomCredential there is no refresh_token or
        expiry to track in V1.
        """
        existing = SlackCredentialRepository.get_by_user_id(db, user_id)

        team = token_response.get("team") or {}
        authed_user = token_response.get("authed_user") or {}

        if existing:
            existing.access_token = token_response["access_token"]
            existing.team_id = team.get("id") or existing.team_id
            existing.team_name = team.get("name", existing.team_name)
            existing.slack_user_id = (
                authed_user.get("id") or existing.slack_user_id
            )
            existing.scopes = token_response.get("scope", "")

            return SlackCredentialRepository.update(db, existing)

        credential = SlackCredential(
            user_id=user_id,
            access_token=token_response["access_token"],
            team_id=team.get("id", ""),
            team_name=team.get("name"),
            slack_user_id=authed_user.get("id", ""),
            scopes=token_response.get("scope", ""),
        )

        return SlackCredentialRepository.create(db, credential)

    @staticmethod
    def disconnect(db: Session, user_id: int) -> None:
        """
        Used by DELETE /slack/disconnect. Removes the stored credential
        row. This does not revoke the token on Slack's side (no
        auth.revoke call is made) - it only stops this app from using
        it, matching the "Disconnect" action shown in the Settings UI.
        """
        credential = SlackCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Slack account is not connected.",
            )

        SlackCredentialRepository.delete(db, credential)

    @staticmethod
    def _build_message(event_label: str, meeting: Meeting) -> str:
        lines = [
            f"Meeting {event_label}: {meeting.title}",
            f"Start: {meeting.start_time}",
            f"End: {meeting.end_time}",
        ]

        # Mirrors EmailService.send_meeting_cancellation, which also
        # omits location for a cancellation notice.
        if event_label != "Cancelled":
            lines.append(f"Location: {meeting.location or 'N/A'}")

        return "\n".join(lines)

    @staticmethod
    def _send_best_effort(
        db: Session,
        meeting: Meeting,
        event_label: str,
    ) -> bool:
        """
        Never raises - a Slack outage, revoked token, or missing
        credential must not turn an already-persisted meeting operation
        into a failed request, mirroring
        EmailService.try_send_meeting_*.
        """
        credential = SlackCredentialRepository.get_by_user_id(
            db,
            meeting.owner_id,
        )

        if credential is None:
            return False

        try:
            SlackAPI.post_message(
                credential=credential,
                text=SlackNotificationService._build_message(
                    event_label,
                    meeting,
                ),
            )
            return True
        except Exception:
            logger.exception(
                "Failed to send Slack notification. meeting_id=%s "
                "event=%s",
                meeting.id,
                event_label,
            )
            return False

    @staticmethod
    def notify_meeting_created(db: Session, meeting: Meeting) -> bool:
        return SlackNotificationService._send_best_effort(
            db,
            meeting,
            "Created",
        )

    @staticmethod
    def notify_meeting_updated(db: Session, meeting: Meeting) -> bool:
        return SlackNotificationService._send_best_effort(
            db,
            meeting,
            "Updated",
        )

    @staticmethod
    def notify_meeting_cancelled(db: Session, meeting: Meeting) -> bool:
        return SlackNotificationService._send_best_effort(
            db,
            meeting,
            "Cancelled",
        )

    @staticmethod
    def send_manual_notification(db: Session, meeting: Meeting) -> None:
        """
        Used by POST /slack/send/{meeting_id}. Unlike the automatic
        hooks above, failures here are surfaced to the caller rather
        than swallowed - this is an explicit, user-triggered action,
        mirroring the manual /zoom/sync and /teams/sync endpoints.
        Sends the same message content (via the shared _build_message
        helper above) as the automatic notifications.
        """
        credential = SlackCredentialRepository.get_by_user_id(
            db,
            meeting.owner_id,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slack account not connected.",
            )

        try:
            SlackAPI.post_message(
                credential=credential,
                text=SlackNotificationService._build_message(
                    "Notification",
                    meeting,
                ),
            )
        except Exception:
            logger.warning(
                "Manual Slack notification failed. meeting_id=%s",
                meeting.id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send the Slack notification.",
            )
