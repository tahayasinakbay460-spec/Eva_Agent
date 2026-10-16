"""Async SQLAlchemy motoru (engine), oturum fabrikası ve tüm modellerin ortak tabanı (Base)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def utcnow_after(previous: datetime | None) -> datetime:
    """Şu an, ama ``previous``'tan kesinlikle daha sonra.

    Mesajlar ve anılar ``created_at``'e göre sıralanır. Windows'ta saat ~15 ms'de bir
    ilerlediği için arka arkaya iki kayıt aynı zaman damgasını alabilir; o zaman sıra
    rastgele UUID'ye kalır ve karışırdı. Bu fonksiyon gerekirse 1 mikrosaniye ekler.
    """
    now = utcnow()
    if previous is not None and now <= previous:
        return previous + timedelta(microseconds=1)
    return now


def create_engine(database_url: str) -> AsyncEngine:
    kwargs: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_async_engine(database_url, **kwargs)
    if engine.dialect.name == "sqlite":
        # SQLite yabancı anahtar kurallarını (ör. "anı silinince vektörü de silinsin")
        # varsayılan olarak UYGULAMAZ; her bağlantıda açıkça açmak gerekir.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI bağımlılığı: her isteğe bir DB oturumu verir (fabrika ``app.state``'ten gelir)."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
