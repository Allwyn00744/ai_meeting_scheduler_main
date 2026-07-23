from datetime import datetime, timedelta, timezone

import logging

import requests
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.calendar.zoom_oauth import ZoomOAuthService
from app.calendar.zoom_api import ZoomAPI
from app.models.zoom_credential import ZoomCredential
from app.repositories.zoom_credential_repository import (
    ZoomCredentialRepository,
)

logger = logging.getLogger(__name__)


class ZoomCalendarService:

    @staticmethod
    def save_zoom_credentials(
        db: Session,
        user_id: int,
        token_response: dict,
    ):
        existing = ZoomCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        expiry = datetime.now(timezone.utc) + timedelta(
            seconds=token_response.get("expires_in", 0)
        )
        scopes = token_response.get("scope", "")

        if existing:
            existing.access_token = token_response["access_token"]
            # Zoom doesn't always return a new refresh_token on every
            # exchange - keep the previous one when absent.
            if token_response.get("refresh_token"):
                existing.refresh_token = token_response["refresh_token"]
            existing.scopes = scopes
            existing.expiry = expiry

            return ZoomCredentialRepository.update(
                db,
                existing,
            )

        credential = ZoomCredential(
            user_id=user_id,
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token"),
            scopes=scopes,
            expiry=expiry,
        )

        return ZoomCredentialRepository.create(
            db,
            credential,
        )

    @staticmethod
    def is_zoom_connected(db: Session, user_id: int) -> bool:
        """
        Cheap, read-only check for whether this user has a stored Zoom
        credential - does not attempt to refresh or validate the
        token. Callers that want to skip Zoom sync entirely (e.g.
        MeetingService, before touching Google/Outlook's flows at all)
        can use this instead of paying for a fetch + refresh attempt.
        """
        return (
            ZoomCredentialRepository.get_by_user_id(db, user_id)
            is not None
        )

    @staticmethod
    def create_zoom_meeting(
        db: Session,
        user_id: int,
        title: str,
        description: str,
        start_time,
        end_time,
    ):
        credential = ZoomCredentialRepository.get_by_user_id(
            db,
            user_id,
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Zoom account not connected.",
            )

        credential = ZoomCalendarService.refresh_zoom_token(
            db,
            credential,
        )

        try:
            meeting = ZoomAPI.create_meeting(
                credential=credential,
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Zoom create_meeting failed. user_id=%s status=%s",
                user_id,
                _response_status(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to create the meeting on Zoom.",
            )

        logger.info(
            "Zoom meeting created. user_id=%s zoom_meeting_id=%s",
            user_id,
            meeting.get("id"),
        )

        return meeting

    @staticmethod
    def update_zoom_meeting(
        db: Session,
        meeting,
    ):
        credential = ZoomCredentialRepository.get_by_user_id(
            db,
            meeting.owner_id,
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Zoom account not connected.",
            )

        credential = ZoomCalendarService.refresh_zoom_token(
            db,
            credential,
        )

        if not meeting.zoom_meeting_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Zoom meeting not found.",
            )

        try:
            ZoomAPI.update_meeting(
                credential=credential,
                meeting_id=meeting.zoom_meeting_id,
                title=meeting.title,
                description=meeting.description or "",
                start_time=meeting.start_time,
                end_time=meeting.end_time,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Zoom update_meeting failed. meeting_id=%s status=%s",
                meeting.id,
                _response_status(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to update the meeting on Zoom.",
            )

        logger.info(
            "Zoom meeting updated. meeting_id=%s zoom_meeting_id=%s",
            meeting.id,
            meeting.zoom_meeting_id,
        )

    @staticmethod
    def delete_zoom_meeting(
        db: Session,
        meeting,
    ):
        credential = ZoomCredentialRepository.get_by_user_id(
            db,
            meeting.owner_id,
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Zoom account not connected.",
            )

        credential = ZoomCalendarService.refresh_zoom_token(
            db,
            credential,
        )

        if not meeting.zoom_meeting_id:
            return

        try:
            ZoomAPI.delete_meeting(
                credential=credential,
                meeting_id=meeting.zoom_meeting_id,
            )
        except requests.exceptions.RequestException as exc:
            status_code = _response_status(exc)

            # Already gone on Zoom's side (e.g. deleted manually by the
            # user in the Zoom app/web portal) - treat as success
            # rather than blocking our own deletion on a stale
            # reference.
            if status_code == 404:
                logger.info(
                    "Zoom meeting already absent. meeting_id=%s "
                    "zoom_meeting_id=%s",
                    meeting.id,
                    meeting.zoom_meeting_id,
                )
                return

            logger.warning(
                "Zoom delete_meeting failed. meeting_id=%s status=%s",
                meeting.id,
                status_code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to delete the meeting on Zoom.",
            )

        logger.info(
            "Zoom meeting deleted. meeting_id=%s zoom_meeting_id=%s",
            meeting.id,
            meeting.zoom_meeting_id,
        )

    @staticmethod
    def refresh_zoom_token(
        db: Session,
        credential: ZoomCredential,
    ):
        expiry = credential.expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        is_expired = (
            expiry is not None and expiry <= datetime.now(timezone.utc)
        )

        if is_expired and credential.refresh_token:
            logger.info(
                "Refreshing expired Zoom OAuth token. user_id=%s",
                credential.user_id,
            )

            token_response = ZoomOAuthService.refresh_access_token(
                credential.refresh_token,
            )

            if (
                "error" in token_response
                or "access_token" not in token_response
            ):
                # Never log the full token_response here - it can
                # include request/correlation details best kept out of
                # logs.
                logger.warning(
                    "Zoom OAuth token refresh failed. user_id=%s "
                    "error=%s",
                    credential.user_id,
                    token_response.get("error"),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Zoom account access has expired or been "
                        "revoked. Please reconnect your Zoom account."
                    ),
                )

            credential.access_token = token_response["access_token"]
            if token_response.get("refresh_token"):
                credential.refresh_token = token_response["refresh_token"]
            credential.expiry = datetime.now(timezone.utc) + timedelta(
                seconds=token_response.get("expires_in", 0)
            )

            credential = ZoomCredentialRepository.update(
                db,
                credential,
            )

            logger.info(
                "Zoom OAuth token refreshed successfully. user_id=%s",
                credential.user_id,
            )

        return credential

    @staticmethod
    def get_connection_status(db: Session, user_id: int) -> dict:
        """
        Used by GET /zoom/status. Returns whether this user has a
        stored Zoom credential, without attempting to refresh or
        validate the token (a cheap, read-only check for the Settings
        UI to render Connected/Not connected).
        """
        return {
            "connected": ZoomCalendarService.is_zoom_connected(
                db,
                user_id,
            ),
        }

    @staticmethod
    def disconnect(db: Session, user_id: int) -> None:
        """
        Used by DELETE /zoom/disconnect. Removes the stored credential
        row. This does not revoke the token on Zoom's side (no token
        revocation call is made) - it only stops this app from using
        it, matching the "Disconnect" action shown in the Settings UI.
        """
        credential = ZoomCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zoom account is not connected.",
            )

        ZoomCredentialRepository.delete(db, credential)


def _response_status(exc: requests.exceptions.RequestException):
    """
    Status code for HTTP error responses (e.g. 404), or None for
    connection/timeout failures that never got a response at all -
    both are surfaced to the caller as a 502, but the status code is
    useful in logs and lets delete treat a 404 as already-deleted.
    """
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)
