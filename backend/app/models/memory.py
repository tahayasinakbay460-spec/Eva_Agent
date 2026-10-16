import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    Date,
    Dialect,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeEngine

from app.database import Base, utcnow
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from app.models.persona import JSONDict


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """EVA'nın kullanıcı hakkında hatırladığı tek bir şey (CLAUDE.md §6).

    Her anı hem bir kullanıcıya hem bir personaya bağlıdır: EVA'ya anlattığın şeyi
    başka bir karakter bilemez, başka bir kullanıcı da asla göremez (§6.5).

    Türler (``kind``):
    - ``episode``: bir olay, yani "anı" ("Geçen yaz Bodrum'a gittik").
    - ``fact``: kalıcı bir bilgi ("Kahveyi sütsüz içer", "Kız kardeşinin adı Elif").
    """

    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_user_persona", "user_id", "persona_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # episode | fact
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Anının ne zaman olduğu (kullanıcı biliyorsa). Kayıt tarihi değil, olay tarihi.
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Anıda geçen kişiler, ör. ["annem", "Elif"].
    people: Mapped[list[str]] = mapped_column(JSONDict, nullable=False, default=list)
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 0 ile 1 arası: ne kadar önemli. Aramada önemli anılar öne çıkar.
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    # Anı nereden geldi: kullanıcı mı ekledi, sohbetten mi çıkarıldı (§6.2).
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # auto | user_added | ...
    # Hassas anılar (sağlık, finans...) Miras'a varsayılan olarak dahil edilmez (§8.1).
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    legacy_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="included")
    # Bu anı hangi sohbetten çıkarıldı (otomatik anılarda). Sohbet silinirse bağ kopar.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # Aramaya hazır metin: içerik + kişiler, Türkçe kurallarıyla küçük harfe çevrilmiş.
    # Kayıttan hemen önce otomatik doldurulur (aşağıdaki olay dinleyicisi); elle yazılmaz.
    # Sohbet sırasında veritabanı sadece mesajdaki kelimeleri içeren anıları getirsin diye var.
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")


class VectorType(TypeDecorator[list[float]]):
    """Vektör sütunu: Postgres'te pgvector'ün ``vector`` tipi, SQLite'ta JSON liste.

    Böylece aynı model hem geliştirmede (SQLite) hem gerçek sunucuda (Postgres) çalışır.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(VECTOR())
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        return [float(x) for x in value]


class MemoryEmbedding(Base):
    """Bir anının vektörü (embedding). Anı silinince bu da silinir (§6.5: vektörler de
    düz metin kadar hassastır, geri çevrilebilir).

    Hangi sağlayıcı/model ile üretildiği saklanır: sağlayıcı değişince eski vektörler
    karşılaştırılamaz, yeniden üretilmeleri gerekir.
    """

    __tablename__ = "memory_embeddings"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(VectorType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


def turkish_lower(text: str) -> str:
    """Python'un ``lower()``'ı "I" harfini "i" yapar; Türkçede "ı" olmalı."""
    return text.replace("I", "ı").replace("İ", "i").lower()


def build_search_text(content: str, people: list[str]) -> str:
    return turkish_lower(" ".join([content, *people]))


@event.listens_for(Memory, "before_insert")
@event.listens_for(Memory, "before_update")
def _fill_search_text(_mapper: object, _connection: object, memory: Memory) -> None:
    memory.search_text = build_search_text(memory.content, list(memory.people or []))
