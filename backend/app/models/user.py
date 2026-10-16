from datetime import datetime

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Internal identifier (random for passkey sign-ups); not shown as a username.
    handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="tr")
    # WebAuthn user handle: random bytes, no personal data (W3C WebAuthn §14.6.1).
    webauthn_user_id: Mapped[bytes | None] = mapped_column(
        LargeBinary(64), unique=True, nullable=True
    )
    # Email + password sign-in (threat model §2). Email is stored normalized (lower-case);
    # only Argon2id hashes are stored, never the password.
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Sign-up declarations (§7 AI disclosure, §12 18+). Null for dev-login users.
    age_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ai_disclosure_accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
