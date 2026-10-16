"""Veritabanı tabanlı iş kuyruğu (ADR 0003).

İş eklemek (``enqueue``) çağıranın veritabanı oturumuna satır ekler ama commit
etmez: iş, onu doğuran değişiklikle aynı commit'te kaydedilir.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import utcnow
from app.models.job import Job

# Bu kadar süredir "çalışıyor" görünen iş, işçisi çökmüş sayılır ve sıraya geri döner.
STALE_AFTER = timedelta(minutes=10)
# İlk tekrar denemeden önce beklenecek süre; her denemede ikiye katlanır.
RETRY_BASE = timedelta(seconds=20)


async def enqueue(
    db: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 5,
) -> None:
    """İşi sıraya ekler (commit çağıranın işi).

    ``dedupe_key`` verilirse ve aynı anahtarla bekleyen bir iş varsa yenisi eklenmez;
    var olanın zamanı yeni ``run_at``'e çekilir (ör. "sohbet sustuktan 10 dk sonra çalış":
    her yeni mesaj sayacı baştan başlatır).
    """
    when = run_at or utcnow()
    if dedupe_key is not None:
        existing = await db.execute(
            select(Job).where(Job.dedupe_key == dedupe_key, Job.status == "pending")
        )
        job = existing.scalar_one_or_none()
        if job is not None:
            job.run_at = when
            job.payload = payload
            return
    db.add(
        Job(
            kind=kind,
            payload=payload,
            run_at=when,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
        )
    )


async def claim(db: AsyncSession) -> Job | None:
    """Zamanı gelmiş bir işi kendine al. Aynı işi iki işçi asla birlikte alamaz."""
    now = utcnow()
    # Çökmüş işçilerden kalan işleri sıraya geri koy.
    await db.execute(
        update(Job)
        .where(Job.status == "running", Job.locked_at < now - STALE_AFTER)
        .values(status="pending", locked_at=None)
        .execution_options(synchronize_session=False)
    )
    candidate = await db.scalar(
        select(Job.id)
        .where(Job.status == "pending", Job.run_at <= now)
        .order_by(Job.run_at)
        .limit(1)
    )
    if candidate is None:
        await db.commit()
        return None
    taken = await db.execute(
        update(Job)
        .where(Job.id == candidate, Job.status == "pending")
        .values(status="running", locked_at=now, attempts=Job.attempts + 1)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if taken.rowcount != 1:  # type: ignore[attr-defined]
        return None  # başka bir işçi bizden önce aldı
    return await db.get(Job, candidate, populate_existing=True)


async def complete(db: AsyncSession, job_id: uuid.UUID) -> None:
    await db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="done", finished_at=utcnow(), locked_at=None)
        .execution_options(synchronize_session=False)
    )
    await db.commit()


async def fail(db: AsyncSession, job: Job, error: BaseException) -> None:
    """Hata: deneme hakkı varsa beklet ve tekrar sıraya koy, yoksa ``failed``."""
    now = utcnow()
    values: dict[str, Any] = {"locked_at": None, "last_error": type(error).__name__[:128]}
    if job.attempts < job.max_attempts:
        values |= {"status": "pending", "run_at": now + RETRY_BASE * (2 ** (job.attempts - 1))}
    else:
        values |= {"status": "failed", "finished_at": now}
    await db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
