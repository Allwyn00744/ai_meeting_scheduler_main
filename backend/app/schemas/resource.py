from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResourceCreate(BaseModel):
    name: str
    resource_type: str
    description: str | None = None
    location: str | None = None


class ResourceUpdate(BaseModel):
    name: str | None = None
    resource_type: str | None = None
    description: str | None = None
    location: str | None = None
    is_active: bool | None = None


class ResourceResponse(BaseModel):
    id: int
    name: str
    resource_type: str
    description: str | None
    location: str | None
    is_active: bool
    created_by_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
