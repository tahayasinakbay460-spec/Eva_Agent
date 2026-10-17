import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow
from app.models.base import UTCDateTime, UUIDPrimaryKeyMixin


class MediaPreference(UUIDPrimaryKeyMixin, Base):
    """Kullanıcının bir persona için seçtiği ses ve yüz (``config/media.yaml`` kataloğundaki
    anahtar ya da ``own`` = kendi rızalı klonu / fotoğrafı). Boş = personanın varsayılanı."""

    __tablename__ = "media_preferences"
    __table_args__ = (UniqueConstraint("user_id", "persona_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    voice_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
