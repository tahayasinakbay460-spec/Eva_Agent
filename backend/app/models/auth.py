import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin


class Passkey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A WebAuthn credential. The public key is not secret; the private key never leaves
    the user's device."""

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
    """A pending WebAuthn ceremony. Single use: ``consumed_at`` is set before verifying.

    ``payload`` carries the sign-up form (display name, declarations) between the
    options and verify calls; it never holds credentials.
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
