from typing import Optional

from pydantic import BaseModel, ConfigDict


class PushSubscriptionKeys(BaseModel):
    """
    Matches the `keys` object of the browser's PushSubscription.toJSON()
    output.
    """

    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    """
    Body for POST /push/subscribe. Mirrors the shape of
    PushSubscription.toJSON() from the browser Push API. is_enabled is
    optional and only takes effect when a subscription with this
    endpoint already exists - it lets the Settings UI's Enable/Disable
    switch reuse this same upsert endpoint instead of a separate route.
    """

    endpoint: str
    keys: PushSubscriptionKeys
    is_enabled: Optional[bool] = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class PushStatusResponse(BaseModel):
    enabled: bool
    subscription_count: int

    model_config = ConfigDict(from_attributes=True)
