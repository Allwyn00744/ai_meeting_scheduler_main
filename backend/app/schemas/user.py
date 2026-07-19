from pydantic import BaseModel, EmailStr, ConfigDict


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    timezone: str = "UTC"


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    timezone: str | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    timezone: str

    model_config = ConfigDict(from_attributes=True)

class PasswordUpdate(BaseModel):
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str