import uuid
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


class DevLoginRequest(BaseModel):
    handle: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=80)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    handle: str
    display_name: str
    locale: str
    email: str | None = None


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


# --- email + password (docs/threat-model.md §2) ------------------------------------

# Stored and compared lower-case so "Ali@x.com" and "ali@x.com" are one account.
Email = Annotated[EmailStr, AfterValidator(lambda v: v.lower())]
NewPassword = Annotated[str, Field(min_length=10, max_length=128)]
Code = Annotated[str, Field(pattern=r"^\d{6}$")]


class PasswordSignUpRequest(BaseModel):
    email: Email
    password: NewPassword
    display_name: str = Field(min_length=1, max_length=80)
    locale: Literal["tr", "en"] = "tr"
    age_confirmed: Literal[True]
    ai_disclosure_accepted: Literal[True]


class PasswordLoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: Email
    locale: Literal["tr", "en"] = "tr"


class CodeFlowOut(BaseModel):
    """A code was (or, for unknown emails, appears to have been) sent."""

    flow_id: uuid.UUID
    method: Literal["email_code"] = "email_code"


class CodeVerifyRequest(BaseModel):
    flow_id: uuid.UUID
    code: Code


class PasswordResetVerifyRequest(BaseModel):
    flow_id: uuid.UUID
    code: Code
    new_password: NewPassword
