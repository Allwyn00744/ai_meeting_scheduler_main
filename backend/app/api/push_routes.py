import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.models.user import User
from app.schemas.push import (
    PushStatusResponse,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
)
from app.services.push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/push",
    tags=["Push Notifications"],
)


@router.get("/vapid-public-key")
def push_vapid_public_key():
    """
    Used by the Settings UI before calling the browser's
    PushManager.subscribe() - the VAPID public key is the
    applicationServerKey it needs, and unlike VAPID_PRIVATE_KEY it is
    safe to expose to any authenticated client.
    """
    return {"vapid_public_key": settings.VAPID_PUBLIC_KEY}


@router.get("/status", response_model=PushStatusResponse)
def push_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PushNotificationService.get_status(db, current_user.id)


@router.post("/subscribe", response_model=PushStatusResponse)
def push_subscribe(
    subscribe: PushSubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    PushNotificationService.subscribe(db, current_user.id, subscribe)

    return PushNotificationService.get_status(db, current_user.id)


@router.delete("/unsubscribe", response_model=PushStatusResponse)
def push_unsubscribe(
    body: PushUnsubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    PushNotificationService.unsubscribe(db, current_user.id, body.endpoint)

    return PushNotificationService.get_status(db, current_user.id)


@router.post("/test")
def send_push_test_notification(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    PushNotificationService.send_test_notification(db, current_user.id)

    return {
        "message": "Push test notification sent successfully",
    }
