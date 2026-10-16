import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.database import utcnow


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class UTCDateTime(TypeDecorator[datetime]):
    """Her veritabanında saat dilimi bilgisi olan (UTC) tarih-saat kolonu.

    PostgreSQL saat dilimini kendisi saklar; SQLite atar, o yüzden okurken UTC'yi geri
    ekliyoruz. Saat dilimi olmayan ("naive") tarihler yazılırken reddedilir; böylece
    kolondaki değerin hangi saate göre olduğu hiç belirsiz kalmaz.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime written to UTCDateTime column")
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"unexpected datetime value {value!r}")
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
