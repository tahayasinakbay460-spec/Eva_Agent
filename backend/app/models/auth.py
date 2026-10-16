import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin


class Passkey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bir WebAuthn kimlik bilgisi (passkey). Açık anahtar gizli değildir; özel anahtar
    kullanıcının cihazından asla çıkmaz."""

    __tablename__ = "passkeys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary(1024), unique=True, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transports: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    aaguid: Mapped[str] = mapped_column(String(36), nullable=False)
    backed_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuthChallenge(UUIDPrimaryKeyMixin, Base):
    """Yarım kalmış bir WebAuthn "töreni" (passkey kayıt/giriş adımları). Tek kullanımlık:
    doğrulamadan önce ``consumed_at`` doldurulur.

    ``payload``, kayıt formunu (görünen ad, beyanlar) options ve verify çağrıları
    arasında taşır; içinde asla kimlik bilgisi tutulmaz.
    """

    __tablename__ = "auth_challenges"

    purpose: Mapped[str] = mapped_column(String(16), nullable=False)  # register | login
    challenge: Mapped[bytes] = mapped_column(LargeBinary(64), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuthCode(UUIDPrimaryKeyMixin, Base):
    """Kayıt, giriş ya da şifre sıfırlama için e-postayla gönderilen 6 haneli kod.

    Yalnızca ``sha256(flow_id:code)`` saklanır. Satırın id'si, istemcinin elindeki akış
    kimliğidir (flow id); ``attempts`` tahmin denemelerini sınırlar, ``consumed_at`` da
    kodu tek kullanımlık yapar.
    """

    __tablename__ = "auth_codes"

    purpose: Mapped[str] = mapped_column(String(16), nullable=False)  # signup | login | reset
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Bekleyen kayıt bilgisi (görünen ad, dil, şifre özeti); şifrenin kendisi asla değil.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
