import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CallCreate(BaseModel):
    persona_id: uuid.UUID | None = None
    mode: Literal["voice", "video"] = "voice"
    # Kendi rızalı ses (ve görüntülüde yüz) klonunla önizleme görüşmesi (Faz 3).
    use_my_media: bool = False


class CallOut(BaseModel):
    """Tarayıcının LiveKit odasına katılması için gereken her şey. Token kısa ömürlü ve
    yalnızca bu odaya, yalnızca mikrofon yayınına izin verir."""

    call_id: uuid.UUID
    conversation_id: uuid.UUID
    mode: Literal["voice", "video"]
    media_source: Literal["persona", "self"]
    livekit_url: str
    token: str
    max_duration_s: int
    idle_timeout_s: int


class CallStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mode: Literal["voice", "video"]
    status: Literal["created", "active", "ended"]
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    end_reason: str | None


class TurnLatencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_id: uuid.UUID
    created_at: datetime
    interrupted: bool
    e2e_ms: float | None
    end_of_turn_ms: float | None
    stt_final_ms: float | None
    llm_ttft_ms: float | None
    tts_ttfb_ms: float | None
    avatar_first_frame_ms: float | None


class StageSummaryOut(BaseModel):
    p50: float | None
    p95: float | None
    count: int


class LatencyReportOut(BaseModel):
    """Gecikme panosu (§4.4): son turların aşama süreleri ve p50/p95 özetleri."""

    stages: dict[str, StageSummaryOut]
    turns: list[TurnLatencyOut]
    targets_ms: dict[str, dict[str, float]]
