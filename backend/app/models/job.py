from datetime import datetime
from typing import Any

from sqlalchemy import Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow
from app.models.base import UTCDateTime, UUIDPrimaryKeyMixin
from app.models.persona import JSONDict


class Job(UUIDPrimaryKeyMixin, Base):
    """Arka planda yapılacak bir iş (ADR 0003). Örnek: "şu anıyı vektöre çevir".

    Durumlar: pending (sırada) → running (bir işçi yapıyor) → done (bitti) ya da
    failed (deneme hakları bitti). ``payload`` sadece ID'ler taşır, içerik değil.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        # İşçinin "sıradaki iş hangisi?" sorusu için.
        Index("ix_jobs_status_run_at", "status", "run_at"),
        # Aynı tekilleştirme anahtarıyla en fazla bir bekleyen iş olabilir.
        Index(
            "uq_jobs_pending_dedupe",
            "dedupe_key",
            unique=True,
            sqlite_where=text("status = 'pending' AND dedupe_key IS NOT NULL"),
            postgresql_where=text("status = 'pending' AND dedupe_key IS NOT NULL"),
        ),
    )

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Sadece hata türü (ör. "ProviderError"); mesaj içerik sızdırabilir, tutulmaz.
    last_error: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
