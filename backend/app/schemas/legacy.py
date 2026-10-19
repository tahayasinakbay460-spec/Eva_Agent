import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.persona.types import ExampleDialog

SynthesisStatus = Literal["none", "pending", "ready", "failed", "not_enough_data"]


class LegacyPersonaOut(BaseModel):
    """Sahibin Miras personası. ``has_draft=False`` iken metin alanları henüz boştur."""

    id: uuid.UUID
    name: str
    status: SynthesisStatus
    has_draft: bool
    identity: str
    personality: str
    speaking_style: str
    example_dialogs: list[ExampleDialog]
    # Miras'a şu an dahil anı sayısı (kapsam ekranı /memories'te, ``legacy_scope`` ile).
    included_memories: int
    # Paylaşım için ikisi de zorunlu (sahibin kararı, ADR 0010).
    voice_ready: bool
    face_ready: bool
    # Alıcıların konuştuğu sürüm; hiç yayınlanmadıysa null.
    published_version: int | None
    # EVA seni paylaşacak kadar tanıyor mu? (Miras'a dahil anı + EVA'ya yazdığın mesaj sayısı)
    memory_count: int
    message_count: int
    min_memories: int
    min_messages: int
    knows_you_enough: bool


class LegacyPublishOut(BaseModel):
    version: int
    memories: int


class LegacyDraftIn(BaseModel):
    identity: str = Field(min_length=1, max_length=2000)
    personality: str = Field(min_length=1, max_length=4000)
    speaking_style: str = Field(min_length=1, max_length=4000)
    example_dialogs: list[ExampleDialog] = Field(default_factory=list, max_length=10)


class LegacyConsentTextOut(BaseModel):
    version: str
    text: str


class LegacyGrantCreate(BaseModel):
    recipient_email: EmailStr
    # Sahip Miras rıza metnini (``GET /legacy/consent-text``) okuyup onayladı.
    consent_accepted: Literal[True]
    consent_text_version: str = Field(min_length=1, max_length=16)


class LegacyGrantOut(BaseModel):
    id: uuid.UUID
    recipient_email: str
    status: Literal["pending", "redeemed", "revoked", "expired"]
    mode: Literal["living", "posthumous"]
    created_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None


class LegacyGrantCreatedOut(LegacyGrantOut):
    """Anahtar yalnızca bu cevapta, bir kez gösterilir; hiçbir yerde saklanmaz."""

    key: str


class LegacyRedeemIn(BaseModel):
    key: str = Field(min_length=10, max_length=80)


class LegacyRedeemStartedOut(BaseModel):
    flow_id: uuid.UUID
    # Kodun gittiği adres, maskeli (ör. a***@ornek.com).
    email_hint: str


class LegacyRedeemVerifyIn(BaseModel):
    flow_id: uuid.UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class LegacyRedeemedOut(BaseModel):
    persona_id: uuid.UUID
    owner_name: str


class SharedLegacyOut(BaseModel):
    """Alıcının açtığı bir Miras. ``status=active`` iken konuşulabilir."""

    access_id: uuid.UUID
    persona_id: uuid.UUID
    owner_name: str
    status: Literal["active", "revoked", "archived"]
    # living: yaşarken paylaşıldı · posthumous: vefat sonrası geldi (silmek e-posta onayı ister)
    mode: Literal["living", "posthumous"]
    since: datetime
    ended_at: datetime | None


# --- vefat sonrası (ADR 0011) -----------------------------------------------------------


class PosthumousHeirOut(BaseModel):
    email: str
    # Etkinleşmede anahtarı gönderildi mi?
    sent: bool


class PosthumousSetupOut(BaseModel):
    state: Literal["off", "armed", "warning", "activated"]
    heirs: list[PosthumousHeirOut]
    trigger: Literal["inactivity", "death_report"] | None
    warning_started_at: datetime | None
    warnings_sent: int
    inactivity_days: int
    warning_days: int
    consent_version: str
    consent_text: str


class PosthumousConfigureIn(BaseModel):
    emails: list[EmailStr] = Field(min_length=1, max_length=5)
    consent_accepted: Literal[True]
    consent_text_version: str = Field(min_length=1, max_length=16)


class HeirOfOut(BaseModel):
    """Seni vefat sonrası alıcı olarak belirlemiş biri (vefatını bildirebilirsin)."""

    owner_id: uuid.UUID
    owner_name: str
    open_report: bool


class DeleteStartedOut(BaseModel):
    flow_id: uuid.UUID
    email_hint: str


class DeleteVerifyIn(BaseModel):
    flow_id: uuid.UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class DeathReportOut(BaseModel):
    id: uuid.UUID
    owner_name: str
    reporter_name: str
    media_type: str
    created_at: datetime
