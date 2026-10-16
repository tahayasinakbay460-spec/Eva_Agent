import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EnrollmentStatus = Literal[
    "collecting", "pending_review", "processing", "active", "rejected", "revoked", "failed"
]


class ConsentTextOut(BaseModel):
    kind: Literal["voice", "face"]
    version: str
    summary: str
    # Ses örneği kaydederken okunacak metin (sadece ses için).
    reading_passage: str | None


class EnrollmentCreate(BaseModel):
    kind: Literal["voice", "face"]
    # Kullanıcının ekranda okuyup onayladığı rıza metninin sürümü; güncel değilse 409.
    consent_text_version: str = Field(min_length=1, max_length=16)
    consent_accepted: Literal[True]


class EnrollmentFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["sample", "consent_recording"]
    media_type: str
    size_bytes: int
    duration_s: int | None
    created_at: datetime


class EnrollmentOut(BaseModel):
    id: uuid.UUID
    kind: Literal["voice", "face"]
    status: EnrollmentStatus
    # Kamerada sesli okunacak cümle (rastgele kod dahil).
    consent_sentence: str
    challenge_code: str
    files: list[EnrollmentFileOut]
    created_at: datetime
    submitted_at: datetime | None
    activated_at: datetime | None
    revoked_at: datetime | None
    reject_reason: str | None


class PreviewRequest(BaseModel):
    sentence: int = Field(ge=0, le=9)


class AdminEnrollmentOut(EnrollmentOut):
    user_id: uuid.UUID
    user_display_name: str


class ApproveRequest(BaseModel):
    """İnceleyicinin tek tek doğruladığı maddeler; hepsi açıkça true olmalı."""

    adult: Literal[True]
    same_person: Literal[True]
    code_matches: Literal[True]
    consent_is_clear: Literal[True]


class RejectRequest(BaseModel):
    reason: Literal[
        "not_adult", "different_person", "code_mismatch", "poor_quality", "not_consenting", "other"
    ]
