from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Stable login identifier. Passkey/MFA identity will attach to this row later (§11.2).
    handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="tr")
