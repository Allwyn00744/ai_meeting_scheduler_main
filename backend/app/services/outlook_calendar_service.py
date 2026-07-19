from datetime import datetime, timedelta, timezone

import logging

import requests
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.calendar.microsoft_oauth import MicrosoftOAuthService
from app.calendar.outlook_calendar import OutlookCalendarAPI
from app.models.outlook_credential import OutlookCredential
from app.repositories.outlook_credential_repository import (
    OutlookCredentialRepository,
)

logger = logging.getLogger(__name__)


class OutlookCalendarService:

    @staticmethod
    def save_outlook_credentials(
        db: Session,
        user_id: int,
        token_response: dict,
    ):
        existing = OutlookCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        expiry = datetime.now(timezone.utc) + timedelta(
            seconds=token_response.get("expires_in", 0)
        )
        scopes = ",".join(token_response.get("scope", "").split())

        if existing:
            existing.access_token = token_response["access_token"]
            # Microsoft doesn't always return a new refresh_token on
            # every exchange - keep the previous one when absent.
            if token_response.get("refresh_token"):
                existing.refresh_token = token_response["refresh_token"]
            existing.scopes = scopes
            existing.expiry = expiry

            return OutlookCredentialRepository.update(
                db,
                existing,
            )

        credential = OutlookCredential(
            user_id=user_id,
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token"),
            scopes=scopes,
            expiry=expiry,
        )

        return OutlookCredentialRepository.create(
            db,
            credential,
        )

    @staticmethod
    def is_outlook_connected(db: Session, user_id: int) -> bool:
        """
        Cheap, read-only check for whether this user has a stored
        Outlook credential - does not attempt to refresh or validate
        the token. Callers that want to skip Outlook sync entirely
        (e.g. MeetingService, before touching Google's flow at all)
        can use this instead of paying for a fetch + refresh attempt.
        """
        return (
            OutlookCredentialRepository.get_by_user_id(db, user_id)
            is not None
        )

    @staticmethod
    def create_outlook_calendar_event(
        db: Session,
        user_id: int,
        title: str,
        description: str,
        start_time,
        end_time,
        location: str | None = None,
        attendee_emails: list[str] | None = None,
    ):
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
            event = OutlookCalendarAPI.create_calendar_event(
                credential=credential,
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                location=location,
                attendee_emails=attendee_emails,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Outlook Calendar create_calendar_event failed. "
                "user_id=%s status=%s",
                user_id,
                _response_status(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to create the event on Outlook Calendar.",
            )

        logger.info(
            "Outlook Calendar event created. user_id=%s event_id=%s",
            user_id,
            event.get("id"),
        )

        return event

    @staticmethod
    def update_outlook_calendar_event(
        db: Session,
        meeting,
    ):
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Outlook event not found.",
            )

        try:
            event = OutlookCalendarAPI.update_calendar_event(
                credential=credential,
                event_id=meeting.outlook_event_id,
                title=meeting.title,
                description=meeting.description or "",
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                location=meeting.location,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Outlook Calendar update_calendar_event failed. "
                "meeting_id=%s status=%s",
                meeting.id,
                _response_status(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to update the event on Outlook Calendar.",
            )

        logger.info(
            "Outlook Calendar event updated. meeting_id=%s event_id=%s",
            meeting.id,
            meeting.outlook_event_id,
        )
        return event

    @staticmethod
    def delete_outlook_calendar_event(
        db: Session,
        meeting,
    ):
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
            OutlookCalendarAPI.delete_calendar_event(
                credential=credential,
                event_id=meeting.outlook_event_id,
            )
        except requests.exceptions.RequestException as exc:
            status_code = _response_status(exc)

            # Already gone on Microsoft's side (e.g. deleted manually
            # by the user in Outlook) - treat as success rather than
            # blocking our own deletion on a stale reference.
            if status_code == 404:
                logger.info(
                    "Outlook Calendar event already absent. "
                    "meeting_id=%s event_id=%s",
                    meeting.id,
                    meeting.outlook_event_id,
                )
                return

            logger.warning(
                "Outlook Calendar delete_calendar_event failed. "
                "meeting_id=%s status=%s",
                meeting.id,
                status_code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to delete the event on Outlook Calendar.",
            )

        logger.info(
            "Outlook Calendar event deleted. meeting_id=%s event_id=%s",
            meeting.id,
            meeting.outlook_event_id,
        )

    @staticmethod
    def refresh_outlook_token(
        db: Session,
        credential: OutlookCredential,
    ):
        expiry = credential.expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        is_expired = (
            expiry is not None and expiry <= datetime.now(timezone.utc)
        )

        if is_expired and credential.refresh_token:
            logger.info(
                "Refreshing expired Outlook OAuth token. user_id=%s",
                credential.user_id,
            )

            token_response = MicrosoftOAuthService.refresh_access_token(
                credential.refresh_token,
            )

            if "error" in token_response:
                # MSAL never raises on OAuth errors - a dead/revoked
                # refresh token comes back as an "invalid_grant"-style
                # error in the response dict, not an exception. Never
                # log the full token_response here - it can include
                # request/correlation details best kept out of logs.
                logger.warning(
                    "Outlook OAuth token refresh failed. user_id=%s "
                    "error=%s",
                    credential.user_id,
                    token_response.get("error"),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Outlook account access has expired or been "
                        "revoked. Please reconnect your Outlook "
                        "account."
                    ),
                )

            credential.access_token = token_response["access_token"]
            if token_response.get("refresh_token"):
                credential.refresh_token = token_response["refresh_token"]
            credential.expiry = datetime.now(timezone.utc) + timedelta(
                seconds=token_response.get("expires_in", 0)
            )

            credential = OutlookCredentialRepository.update(
                db,
                credential,
            )

            logger.info(
                "Outlook OAuth token refreshed successfully. "
                "user_id=%s",
                credential.user_id,
            )

        return credential

    @staticmethod
    def get_connection_status(db: Session, user_id: int) -> dict:
        """
        Used by GET /outlook/status. Returns whether this user has a
        stored Outlook credential, without attempting to refresh or
        validate the token (a cheap, read-only check for the Settings
        UI to render Connected/Not connected).
        """
        return {
            "connected": OutlookCalendarService.is_outlook_connected(
                db,
                user_id,
            ),
        }

    @staticmethod
    def disconnect(db: Session, user_id: int) -> None:
        """
        Used by DELETE /outlook/disconnect. Removes the stored
        credential row. This does not revoke the token on Microsoft's
        side (no token revocation call is made) - it only stops this
        app from using it, matching the "Disconnect" action shown in
        the Settings UI.
        """
        credential = OutlookCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outlook account is not connected.",
            )

        OutlookCredentialRepository.delete(db, credential)


def _response_status(exc: requests.exceptions.RequestException):
    """
    Status code for HTTP error responses (e.g. 404), or None for
    connection/timeout failures that never got a response at all -
    both are surfaced to the caller as a 502, but the status code is
    useful in logs and lets delete treat a 404 as already-deleted.
    """
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)
