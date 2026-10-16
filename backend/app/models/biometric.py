"""Rızalı ses/yüz kaydı (CLAUDE.md §4.5, §11.3; Faz 3).

Bir **kayıt** (``BiometricEnrollment``) bir kullanıcının tek bir türdeki (ses ya da yüz) rızalı
örneklerini ve sağlayıcıdaki klonunu bir arada tutar; CLAUDE.md'deki ``voice_profiles`` /
``avatar_profiles`` burada ``kind`` alanıyla tek tabloda (ADR 0006).

Durumlar: collecting (örnekler toplanıyor) → pending_review (gönderildi, inceleme bekliyor)
→ processing (onaylandı, klon oluşturuluyor) → active. Yan yollar: rejected, revoked, failed.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from app.models.persona import JSONDict

OPEN_STATUSES = ("collecting", "pending_review", "processing", "active")


class BiometricEnrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "biometric_enrollments"
    __table_args__ = (Index("ix_biometric_enrollments_user_kind", "user_id", "kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # voice | face
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="collecting")
    # Rıza cümlesinde sesli okunan rastgele kod (tekrar oynatmaya karşı). Gizli değil: kişi onu
    # kamerada okuyor; yalnızca bu kayda özgü olması önemli.
    challenge_code: Mapped[str] = mapped_column(String(6), nullable=False)
    consent_text_version: Mapped[str] = mapped_column(String(16), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Red sebebi kodu (ör. "not_adult", "different_person"); serbest metin değil.
    reject_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class EnrollmentSample(UUIDPrimaryKeyMixin, Base):
    """Şifreli depodaki tek bir dosya: ses/yüz örneği ya da rıza videosu. İçerik burada değil,
    şifreli depoda (``blob_key``); burada sadece ne olduğu ve özeti var."""

    __tablename__ = "enrollment_samples"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("biometric_enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), nullable=False)  # sample | consent_recording
    blob_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Tarayıcının bildirdiği süre (saniye). Sunucu sesi çözmediği için tavsiye niteliğinde;
    # inceleyici zaten dinliyor.
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ProviderAsset(UUIDPrimaryKeyMixin, Base):
    """Bir kaydın sağlayıcıdaki klonu: yalnızca eşleme (iç kayıt ↔ sağlayıcı id'si, §4.2).
    Ham örnekler bizde durur; sağlayıcı değişirse klon kendi örneklerimizden yeniden üretilir.
    Silinince satır kalır (kanıt), durumu ``deleted`` olur."""

    __tablename__ = "provider_assets"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("biometric_enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # voice | avatar
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Consent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Amaç bazlı rıza (§11.3): ses klonu ve yüz avatarı ayrı ayrı onaylanır, ayrı ayrı geri
    alınır. Bugünkü durum burada; tarihçe ``consent_records``'ta."""

    __tablename__ = "consents"
    __table_args__ = (Index("ix_consents_user_purpose", "user_id", "purpose"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)  # voice_clone | face_avatar
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("biometric_enrollments.id", ondelete="CASCADE"), nullable=False
    )
    text_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # granted | revoked
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ConsentRecord(UUIDPrimaryKeyMixin, Base):
    """Değiştirilemez rıza kanıtı (§11.3): kim, ne zaman, hangi olay, hangi metin sürümü,
    metnin ve kanıtın (rıza videosu) özeti. Yalnızca eklenir; güncelleme ve silme engelli."""

    __tablename__ = "consent_records"

    consent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("consents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # granted | approved | rejected | revoked
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    text_version: Mapped[str] = mapped_column(String(16), nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Yalnızca eklenen denetim kaydı (§4.5): hassas işlemler kim tarafından, ne zaman yapıldı.
    İçerik, kod, dosya ya da kişisel veri yazılmaz; ``meta`` sadece kodlar/id'ler taşır."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AppendOnlyError(RuntimeError):
    pass


def _forbid_change(_mapper: object, _connection: object, target: object) -> None:
    raise AppendOnlyError(f"{type(target).__name__} rows are append-only")


for _model in (ConsentRecord, AuditLog):
    event.listen(_model, "before_update", _forbid_change)
    event.listen(_model, "before_delete", _forbid_change)
