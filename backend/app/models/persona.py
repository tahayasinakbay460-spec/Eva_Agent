import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

JSONDict = JSON().with_variant(JSONB(), "postgresql")


class Persona(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single abstraction for EVA, characters and legacy personas (CLAUDE.md §4.5)."""

    __tablename__ = "personas"

    type: Mapped[str] = mapped_column(String(16), nullable=False)  # eva | character | legacy
    # NULL owner = system persona available to everyone (the default EVA).
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    slug: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)
