import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow
from app.models.base import UTCDateTime, UUIDPrimaryKeyMixin


class CallSession(UUIDPrimaryKeyMixin, Base):
    """Bir sesli/görüntülü görüşme (LiveKit odası). Konuşmanın kendisi ``messages``'ta durur
    (kanal ``voice``); burası yalnızca görüşmenin kaydı: ne zaman, ne kadar, nasıl bitti.

    Durumlar: created (token verildi) → active (ajan bağlandı) → ended.
    """

    __tablename__ = "call_sessions"
    __table_args__ = (Index("ix_call_sessions_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)  # voice | video
    # persona: personanın kendi sesi/yüzü · self: kullanıcının kendi rızalı klonu (önizleme, Faz 3)
    media_source: Mapped[str] = mapped_column(
        String(8), nullable=False, default="persona", server_default="persona"
    )
    room_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="created")
    max_duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    idle_timeout_s: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # user | idle | max_duration | disconnected | replaced | error
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)


class TurnLatency(UUIDPrimaryKeyMixin, Base):
    """Bir görüşme turunun aşama süreleri (milisaniye; §4.4 gecikme bütçesi). İçerik yok,
    sadece sayılar."""

    __tablename__ = "turn_latencies"
    __table_args__ = (Index("ix_turn_latencies_user_created", "user_id", "created_at"),)

    call_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Kullanıcı sustuktan sonra "tur bitti" kararına kadar geçen süre.
    end_of_turn_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Kullanıcı sustuktan sonra kesin metnin gelmesine kadar geçen süre.
    stt_final_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tts_ttfb_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    avatar_first_frame_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Kullanıcı sustu → EVA konuşmaya başladı (asıl hedef: p50 < 800 ms).
    e2e_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    interrupted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
