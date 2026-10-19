import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

JSONDict = JSON().with_variant(JSONB(), "postgresql")


class Persona(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """EVA, karakterler ve Miras personaları için tek ortak model (CLAUDE.md §4.5)."""

    __tablename__ = "personas"

    type: Mapped[str] = mapped_column(String(16), nullable=False)  # eva | character | legacy
    # Sahibi NULL = herkesin kullanabildiği sistem personası (varsayılan EVA).
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    slug: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)
    # Karakter Stüdyosu (ADR 0009). private: yalnızca sahibi · public: herkes kullanabilir.
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", server_default="private", index=True
    )
    # Karakterin yüz görseli: sahibinin veri anahtarıyla şifreli, "media" kovasında.
    face_blob_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    face_media_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Karakterin varsayılan sesi (config/media.yaml anahtarı); boş = EVA'nın varsayılanı.
    voice_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
