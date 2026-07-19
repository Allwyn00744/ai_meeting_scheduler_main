from typing import Optional

from pydantic import BaseModel, ConfigDict


class WhatsAppSettingsResponse(BaseModel):
    enabled: bool
    phone_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WhatsAppSettingsUpdate(BaseModel):
    phone_number: Optional[str] = None
    is_enabled: Optional[bool] = None


class SendWhatsAppRequest(BaseModel):
    """
    Optional body for POST /whatsapp/send/{meeting_id}. When message is
    omitted, the same auto-generated content used by the automatic
    create/update/cancel notifications is sent (see
    WhatsAppNotificationService._build_message).
    """

    message: Optional[str] = None
