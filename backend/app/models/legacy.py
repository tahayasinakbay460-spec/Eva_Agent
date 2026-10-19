"""Miras tabloları (CLAUDE.md §4.5, §8; ADR 0010)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow
from app.models.base import UTCDateTime, UUIDPrimaryKeyMixin

JSONDict = JSON().with_variant(JSONB(), "postgresql")


class PersonaVersion(UUIDPrimaryKeyMixin, Base):
    """Bir personanın salt-okunur anlık görüntüsü. Miras alıcısı her zaman yayınlanmış bir
    sürümle konuşur; sahibin sonraki düzenlemeleri yeni sürüm yayınlanana kadar alıcıya gitmez."""

    __tablename__ = "persona_versions"
    __table_args__ = (UniqueConstraint("persona_id", "version"),)

    persona_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # PersonaDefinition (kapsamdaki anılar ``canon_memories`` olarak içinde).
    definition: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class LegacyGrant(UUIDPrimaryKeyMixin, Base):
    """Bir alıcıya gönderilen tek kullanımlık Miras anahtarı. Anahtarın kendisi değil, yalnızca
    biberli HMAC özeti saklanır (§8.3)."""

    __tablename__ = "legacy_grants"
    __table_args__ = (Index("ix_legacy_grants_owner_status", "owner_id", "status"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    recipient_email: Mapped[str] = mapped_column(String(254), nullable=False)
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pending|redeemed|revoked
    # Sahibin bu paylaşım için onayladığı Miras rıza metninin sürümü (amaç: legacy_share).
    consent_text_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    redeemed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LegacyAccess(UUIDPrimaryKeyMixin, Base):
    """Alıcının Miras personasına erişimi. Sohbet ve görüşme her istekte buna bakar."""

    __tablename__ = "legacy_access"
    __table_args__ = (Index("ix_legacy_access_recipient_persona", "recipient_id", "persona_id"),)

    grant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("legacy_grants.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # active | revoked | archived
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LegacyRedeemFailure(UUIDPrimaryKeyMixin, Base):
    """Başarısız anahtar denemesi (hesap başına kilit için). Anahtarın kendisi yazılmaz."""

    __tablename__ = "legacy_redeem_failures"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, index=True
    )
