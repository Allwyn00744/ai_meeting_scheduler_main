from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ParticipantCreate(BaseModel):
    user_id: int


class ParticipantUpdate(BaseModel):
    status: str


class ParticipantResponse(BaseModel):
    id: int
    meeting_id: int
    user_id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)