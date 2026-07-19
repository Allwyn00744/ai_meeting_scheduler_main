import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.whatsapp import (
    SendWhatsAppRequest,
    WhatsAppSettingsResponse,
    WhatsAppSettingsUpdate,
)
from app.services.meeting_service import MeetingService
from app.services.whatsapp_notification_service import (
    WhatsAppNotificationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/whatsapp",
    tags=["WhatsApp Notifications"],
)


@router.get("/status", response_model=WhatsAppSettingsResponse)
def whatsapp_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return WhatsAppNotificationService.get_status(db, current_user.id)


@router.put("/settings", response_model=WhatsAppSettingsResponse)
def update_whatsapp_settings(
    update: WhatsAppSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    WhatsAppNotificationService.update_settings(
        db,
        current_user.id,
        update,
    )

    return WhatsAppNotificationService.get_status(db, current_user.id)


@router.post("/send/{meeting_id}")
def send_whatsapp_notification(
    meeting_id: int,
    body: Optional[SendWhatsAppRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.send_whatsapp_notification(
        db,
        meeting_id,
        current_user,
        body.message if body else None,
    )


@router.post("/test")
def send_whatsapp_test_notification(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    WhatsAppNotificationService.send_test_message(db, current_user.id)

    return {
        "message": "WhatsApp test notification sent successfully",
    }
