import logging

import requests
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.calendar.teams_api import TeamsMeetingAPI
from app.repositories.outlook_credential_repository import (
    OutlookCredentialRepository,
)
from app.services.outlook_calendar_service import OutlookCalendarService

logger = logging.getLogger(__name__)


class TeamsMeetingService:
    """
    Microsoft Teams Integration V1. Deliberately has no credential
    model/repository or OAuth flow of its own - Teams meetings are
    Outlook calendar events (identified by the existing
    outlook_event_id) with isOnlineMeeting/onlineMeetingProvider set on
    them, so every Graph call here is authenticated with the same
    OutlookCredential row and refreshed via
    OutlookCalendarService.refresh_outlook_token.
    """

    @staticmethod
    def is_teams_available(db: Session, user_id: int) -> bool:
        """
        Teams is available whenever Outlook is connected - there is no
        independent Teams connection state to check.
        """
        return OutlookCalendarService.is_outlook_connected(db, user_id)

    @staticmethod
    def get_connection_status(db: Session, user_id: int) -> dict:
        """
        Used by GET /teams/status. "connected" mirrors Outlook's own
        connection state (see is_teams_available above) - there is no
        separate /teams/connect flow to report on.
        """
        return {
            "connected": TeamsMeetingService.is_teams_available(
                db,
                user_id,
            ),
        }

    @staticmethod
    def enable_teams_meeting(
        db: Session,
        user_id: int,
        event_id: str,
    ) -> dict:
        """
        Turns the Outlook event identified by event_id into a Teams
        meeting. Used both by the automatic best-effort hook (right
        after an Outlook event is created for a meeting) and by the
        manual POST/PUT /teams/sync/{meeting_id} endpoints.
        """
        credential = OutlookCredentialRepository.get_by_user_id(
            db,
            user_id,
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Outlook account not connected.",
            )

        credential = OutlookCalendarService.refresh_outlook_token(
            db,
            credential,
        )

        try:
            event = TeamsMeetingAPI.enable_teams_meeting(
                credential=credential,
                event_id=event_id,
            )
        except requests.exceptions.RequestException as exc:
            status_code = _response_status(exc)

            # A stale token that predates the OnlineMeetings.ReadWrite
            # scope (see MICROSOFT_SCOPES in core/config.py) surfaces
            # here as a 403 - reconnecting is the only fix, since
            # scopes are fixed at consent time and can't be upgraded
            # via a refresh token.
            if status_code == 403:
                logger.warning(
                    "Microsoft Teams enable failed due to insufficient "
                    "Graph permissions. user_id=%s event_id=%s",
                    user_id,
                    event_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Microsoft Teams meetings require additional "
                        "Outlook permissions. Please reconnect your "
                        "Outlook account to enable Teams meetings."
                    ),
                )

            logger.warning(
                "Microsoft Teams enable_teams_meeting failed. "
                "user_id=%s event_id=%s status=%s",
                user_id,
                event_id,
                status_code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to enable the Microsoft Teams meeting.",
            )

        logger.info(
            "Microsoft Teams meeting enabled. user_id=%s event_id=%s",
            user_id,
            event_id,
        )

        return event

    @staticmethod
    def disable_teams_meeting(db: Session, meeting) -> None:
        """
        Used by DELETE /teams/sync/{meeting_id}. Turns Teams off for
        the meeting's existing Outlook event without deleting that
        event - the Outlook calendar sync itself is untouched.
        """
        credential = OutlookCredentialRepository.get_by_user_id(
            db,
            meeting.owner_id,
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Outlook account not connected.",
            )

        credential = OutlookCalendarService.refresh_outlook_token(
            db,
            credential,
        )

        if not meeting.outlook_event_id:
            return

        try:
            TeamsMeetingAPI.disable_teams_meeting(
                credential=credential,
                event_id=meeting.outlook_event_id,
            )
        except requests.exceptions.RequestException as exc:
            status_code = _response_status(exc)

            # Already gone on Microsoft's side (e.g. the Outlook event
            # was deleted manually) - treat as success rather than
            # blocking our own unlink on a stale reference.
            if status_code == 404:
                logger.info(
                    "Outlook event already absent, nothing to unlink. "
                    "meeting_id=%s event_id=%s",
                    meeting.id,
                    meeting.outlook_event_id,
                )
                return

            logger.warning(
                "Microsoft Teams disable_teams_meeting failed. "
                "meeting_id=%s status=%s",
                meeting.id,
                status_code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to remove the Microsoft Teams meeting.",
            )

        logger.info(
            "Microsoft Teams meeting disabled. meeting_id=%s event_id=%s",
            meeting.id,
            meeting.outlook_event_id,
        )


def _response_status(exc: requests.exceptions.RequestException):
    """
    Status code for HTTP error responses (e.g. 403, 404), or None for
    connection/timeout failures that never got a response at all.
    """
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)
