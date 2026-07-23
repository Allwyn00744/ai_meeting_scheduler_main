from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


def normalize_external_guest_emails(
    emails: list[EmailStr],
) -> list[str]:
    """
    Pure normalization for external guest email input, shared by
    MeetingCreate and ScheduleMeetingRequest.

    - Strips whitespace and lowercases each address.
    - Deduplicates the normalized values, preserving first-seen order.

    This performs no database access and no identity-collision checks
    (owner email, registered participant email) - those require a
    Session/current_user and are handled by ExternalGuestService.
    """
    normalized: list[str] = []
    seen: set[str] = set()

    for email in emails:
        candidate = str(email).strip().lower()

        if candidate in seen:
            continue

        seen.add(candidate)
        normalized.append(candidate)

    return normalized


class ExternalGuestResponse(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
