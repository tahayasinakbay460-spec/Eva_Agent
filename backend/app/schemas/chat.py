import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    persona_id: uuid.UUID | None = None  # None -> default EVA


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    persona_id: uuid.UUID
    channel: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    channel: str
    interrupted: bool
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    # Client-generated; lets a retried request replay instead of double-sending (§10).
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


# --- SSE payloads (documented here so the OpenAPI schema carries them) ----------


class SSEMessageStart(BaseModel):
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID


class SSEDelta(BaseModel):
    text: str


class SSEDone(BaseModel):
    assistant_message_id: uuid.UUID
    stop_reason: Literal["end_turn", "max_tokens", "refusal"]
    interrupted: bool


class SSEError(BaseModel):
    code: Literal["provider_error", "internal_error"]
    retryable: bool


class SSEEnvelope(BaseModel):
    """Not sent on the wire; registers the SSE payload schemas in OpenAPI so the TS client
    gets their types. Each event carries exactly one of these as its ``data``."""

    message_start: SSEMessageStart | None = None
    delta: SSEDelta | None = None
    done: SSEDone | None = None
    error: SSEError | None = None
