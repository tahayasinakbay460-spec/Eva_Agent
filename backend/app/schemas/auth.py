import uuid

from pydantic import BaseModel, ConfigDict, Field


class DevLoginRequest(BaseModel):
    handle: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=80)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    handle: str
    display_name: str
    locale: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    user: UserOut
