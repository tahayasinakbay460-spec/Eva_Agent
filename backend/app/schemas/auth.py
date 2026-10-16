import uuid
from datetime import datetime
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
    role: Literal["user", "admin"] = "user"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    user: UserOut


class PasskeySignUpRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    locale: Literal["tr", "en"] = "tr"
    # İkisi de açıkça true olmalı (§12 18+, §7 yapay zekâ bildirimi); başka her değer 422 olur.
    age_confirmed: Literal[True]
    ai_disclosure_accepted: Literal[True]


class PasskeyOptionsOut(BaseModel):
    """Tarayıcıdaki ``navigator.credentials.create/get`` için seçenekler + akışın id'si."""

    flow_id: uuid.UUID
    options: dict[str, Any]


class PasskeyVerifyRequest(BaseModel):
    flow_id: uuid.UUID
    # Tarayıcının ürettiği PublicKeyCredential (JSON); yapısını py_webauthn doğrular.
    credential: dict[str, Any]


# --- e-posta + şifre (docs/threat-model.md §2) ------------------------------------

# Küçük harfle saklanır ve karşılaştırılır; "Ali@x.com" ile "ali@x.com" aynı hesaptır.
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
    """Kod gönderildi (kayıtlı olmayan e-postalarda ise gönderilmiş *gibi* görünür; böylece
    hangi e-postanın kayıtlı olduğu dışarıdan anlaşılmaz)."""

    flow_id: uuid.UUID
    method: Literal["email_code"] = "email_code"


class CodeVerifyRequest(BaseModel):
    flow_id: uuid.UUID
    code: Code


class PasswordResetVerifyRequest(BaseModel):
    flow_id: uuid.UUID
    code: Code
    new_password: NewPassword


# --- adım-yukarı doğrulama (§11.2) ------------------------------------------------


class StepUpStatusOut(BaseModel):
    """Bu oturumda hassas işlem yapılabilir mi, ve kullanıcı hangi yöntemlerle onaylayabilir."""

    valid_until: datetime | None
    methods: list[Literal["passkey", "password"]]


class StepUpPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
