from pydantic import BaseModel, ConfigDict


class KPIResponse(BaseModel):
    meetings_scheduled: int
    conflicts_avoided: int
    time_saved_minutes: int

    model_config = ConfigDict(from_attributes=True)
