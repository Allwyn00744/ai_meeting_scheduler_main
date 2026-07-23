from datetime import time, datetime

from pydantic import BaseModel, ConfigDict


class AvailabilityCreate(BaseModel):
    day_of_week: str
    start_time: time
    end_time: time
    is_available: bool = True


class AvailabilityUpdate(BaseModel):
    day_of_week: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    is_available: bool | None = None


class AvailabilityResponse(BaseModel):
    id: int
    user_id: int
    day_of_week: str
    start_time: time
    end_time: time
    is_available: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)