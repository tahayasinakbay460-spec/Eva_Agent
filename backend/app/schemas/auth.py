import uuid
from typing import Any, Literal

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


class PasskeySignUpRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    locale: Literal["tr", "en"] = "tr"
    # Both must be explicitly true (§12 18+, §7 AI disclosure); anything else is a 422.
    age_confirmed: Literal[True]
    ai_disclosure_accepted: Literal[True]


class PasskeyOptionsOut(BaseModel):
    """Options for ``navigator.credentials.create/get`` plus the flow to finish."""

    flow_id: uuid.UUID
    options: dict[str, Any]


class PasskeyVerifyRequest(BaseModel):
    flow_id: uuid.UUID
    # The browser's PublicKeyCredential as JSON; structure is verified by py_webauthn.
    credential: dict[str, Any]
