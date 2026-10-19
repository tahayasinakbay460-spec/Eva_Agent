"""Arka plan işlerinin kendisi. Her işleyici tekrar çalıştırılabilir (idempotent) olmalı:
işçi çökerse aynı iş ikinci kez gelebilir.
"""

import uuid
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import delete, select

from app.core.ratelimit import MemoryRateLimiter
from app.database import utcnow
from app.legacy.keys import pepper_from_settings
from app.models.biometric import OPEN_STATUSES, BiometricEnrollment, EnrollmentSample, ProviderAsset
from app.models.memory import Memory, MemoryEmbedding
from app.providers.base import AvatarEnrollmentProvider, ProviderError, VoiceEnrollmentProvider
from app.providers.base import EnrollmentSample as ProviderSample
from app.providers.registry import create_adapter
from app.services import (
    audit,
    legacy_posthumous_service,
    legacy_service,
    memory_extraction,
    password_auth_service,
)
from app.worker import queue
from app.worker.jobs import (
    BIOMETRIC_CREATE_ASSET,
    BIOMETRIC_PURGE,
    EMBED_MEMORY,
    EXTRACT_MEMORIES,
    LEGACY_POSTHUMOUS_SWEEP,
    LEGACY_SYNTHESIZE,
)
from app.worker.runner import WorkerContext, handler


def embedding_text(memory: Memory) -> str:
    """Vektöre çevrilecek metin: içerik + kişiler (kişiyle sorulunca da bulunsun)."""
    if memory.people:
        return f"{memory.content} ({', '.join(memory.people)})"
    return memory.content


@handler(EMBED_MEMORY)
async def embed_memory(ctx: WorkerContext, payload: dict[str, Any]) -> None:
    """Bir anıyı vektöre çevirip saklar. Anı bu arada silindiyse hiçbir şey yapmaz."""
    memory_id = uuid.UUID(str(payload["memory_id"]))
    async with ctx.session_factory() as db:
        memory = await db.get(Memory, memory_id)
        if memory is None:
            return
        provider = ctx.registry.embedding("memory")
        (vector,) = await provider.embed([embedding_text(memory)], purpose="document")
        # Varsa eskisini sil, yenisini yaz: aynı iş iki kez gelse de sonuç aynı.
        await db.execute(delete(MemoryEmbedding).where(MemoryEmbedding.memory_id == memory_id))
        db.add(
            MemoryEmbedding(
                memory_id=memory_id,
                provider=provider.name,
                dimensions=len(vector),
                vector=vector,
            )
        )
        await db.commit()


@handler(EXTRACT_MEMORIES)
async def extract_memories(ctx: WorkerContext, payload: dict[str, Any]) -> None:
    """Sohbetin işlenmemiş kısmından anı çıkarır (bkz. services/memory_extraction.py)."""
    conversation_id = uuid.UUID(str(payload["conversation_id"]))
    async with ctx.session_factory() as db:
        await memory_extraction.extract(db, ctx.registry, conversation_id)


@handler(LEGACY_SYNTHESIZE)
async def legacy_synthesize(ctx: WorkerContext, payload: dict[str, Any]) -> None:
    """Miras kişilik taslağı (bkz. services/legacy_service.py)."""
    persona_id = uuid.UUID(str(payload["persona_id"]))
    async with ctx.session_factory() as db:
        await legacy_service.run_synthesis(db, ctx.registry, persona_id)


@handler(LEGACY_POSTHUMOUS_SWEEP)
async def legacy_posthumous_sweep(ctx: WorkerContext, payload: dict[str, Any]) -> None:
    """Vefat sonrası Miras taraması; bitince bir sonrakini sıraya koyar (ADR 0011)."""
    deps = password_auth_service.Deps(
        messaging=ctx.registry.messaging(), limiter=MemoryRateLimiter()
    )
    async with ctx.session_factory() as db:
        await legacy_posthumous_service.sweep(
            db, ctx.settings, deps, pepper_from_settings(ctx.settings)
        )
        await queue.enqueue(
            db,
            LEGACY_POSTHUMOUS_SWEEP,
            {},
            run_at=utcnow() + timedelta(seconds=ctx.settings.legacy_sweep_interval_s),
            dedupe_key=LEGACY_POSTHUMOUS_SWEEP,
        )
        await db.commit()


# --- biyometrik kayıt (Faz 3) ---------------------------------------------------------


def _voice_provider(ctx: WorkerContext, name: str | None = None) -> VoiceEnrollmentProvider:
    configured = ctx.registry.voice_enrollment()
    if name is None or name == configured.name:
        return configured
    # Klon başka bir sağlayıcıda oluşturulmuşsa (config sonradan değiştiyse) onunla sil.
    return cast(VoiceEnrollmentProvider, create_adapter("voice_enrollment", name))


def _avatar_provider(ctx: WorkerContext, name: str | None = None) -> AvatarEnrollmentProvider:
    configured = ctx.registry.avatar_enrollment()
    if name is None or name == configured.name:
        return configured
    return cast(AvatarEnrollmentProvider, create_adapter("avatar_enrollment", name))


@handler(BIOMETRIC_CREATE_ASSET)
async def create_biometric_asset(ctx: WorkerContext, payload: dict[str, Any]) -> None:
    """Onaylanmış kaydın örneklerinden sağlayıcıda klon oluşturur. Sağlayıcıya kişisel veri
    gitmez: etiket sadece kayıt id'si."""
    enrollment_id = uuid.UUID(str(payload["enrollment_id"]))
    samples: list[ProviderSample] = []
    async with ctx.session_factory() as db:
        enrollment = await db.get(BiometricEnrollment, enrollment_id)
        if enrollment is None or enrollment.status != "processing":
            return
        existing = await db.scalar(
            select(ProviderAsset).where(
                ProviderAsset.enrollment_id == enrollment_id, ProviderAsset.status == "active"
            )
        )
        if existing is None:
            rows = (
                await db.execute(
                    select(EnrollmentSample).where(
                        EnrollmentSample.enrollment_id == enrollment_id,
                        EnrollmentSample.role == "sample",
                    )
                )
            ).scalars()
            for row in list(rows):
                data = await ctx.store.get(db, enrollment.user_id, "biometric", row.blob_key)
                samples.append(ProviderSample(data, row.media_type))
        kind = enrollment.kind

    if existing is None:
        label = f"eva-{enrollment_id}"
        try:
            if kind == "voice":
                ref = await _voice_provider(ctx).create_voice(samples, label=label)
            else:
                ref = await _avatar_provider(ctx).create_avatar(samples, label=label)
        except ProviderError as exc:
            if exc.retryable:
                raise  # işçi artan beklemeyle tekrar dener
            await _mark_failed(ctx, enrollment_id)
            return
        async with ctx.session_factory() as db:
            db.add(
                ProviderAsset(
                    enrollment_id=enrollment_id,
                    kind="voice" if kind == "voice" else "avatar",
                    provider=ref.provider,
                    asset_id=ref.asset_id,
                )
            )
            await db.commit()

    async with ctx.session_factory() as db:
        current = await db.get(BiometricEnrollment, enrollment_id, populate_existing=True)
        if current is None:
            return
        if current.status == "processing":
            current.status = "active"
            current.activated_at = utcnow()
            audit.record(
                db,
                action="biometric.activated",
                target_type="biometric_enrollment",
                target_id=enrollment_id,
                user_id=current.user_id,
                actor_id=None,
                meta={"kind": kind},
            )
        else:
            # Klon oluşturulurken rıza geri alındı: yeni klonu da hemen sil.
            await queue.enqueue(db, BIOMETRIC_PURGE, {"enrollment_id": str(enrollment_id)})
        await db.commit()


async def _mark_failed(ctx: WorkerContext, enrollment_id: uuid.UUID) -> None:
    async with ctx.session_factory() as db:
        enrollment = await db.get(BiometricEnrollment, enrollment_id)
        if enrollment is None or enrollment.status != "processing":
            return
        enrollment.status = "failed"
        audit.record(
            db,
            action="biometric.failed",
            target_type="biometric_enrollment",
            target_id=enrollment_id,
            user_id=enrollment.user_id,
            actor_id=None,
            meta={"kind": enrollment.kind},
        )
        await queue.enqueue(db, BIOMETRIC_PURGE, {"enrollment_id": str(enrollment_id)})
        await db.commit()


@handler(BIOMETRIC_PURGE)
async def purge_biometric(ctx: WorkerContext, payload: dict[str, Any]) -> None:
    """Klonu sağlayıcıdan siler (idempotent; hata olursa iş tekrar denenir) ve ham dosyaları
    imha eder. Rıza kaydı ve özetleri kanıt olarak kalır; dosyaların kendisi kalmaz."""
    enrollment_id = uuid.UUID(str(payload["enrollment_id"]))
    async with ctx.session_factory() as db:
        enrollment = await db.get(BiometricEnrollment, enrollment_id)
        if enrollment is None or enrollment.status in OPEN_STATUSES:
            return
        assets = (
            await db.execute(
                select(ProviderAsset).where(
                    ProviderAsset.enrollment_id == enrollment_id, ProviderAsset.status != "deleted"
                )
            )
        ).scalars()
        for asset in list(assets):
            if asset.kind == "voice":
                await _voice_provider(ctx, asset.provider).delete_voice(asset.asset_id)
            else:
                await _avatar_provider(ctx, asset.provider).delete_avatar(asset.asset_id)
            asset.status = "deleted"
            asset.deleted_at = utcnow()
            await db.commit()  # her silinen klon hemen işaretlensin (tekrar denemede atlanır)

        files = (
            await db.execute(
                select(EnrollmentSample).where(EnrollmentSample.enrollment_id == enrollment_id)
            )
        ).scalars()
        removed = 0
        for sample in list(files):
            await ctx.store.delete("biometric", sample.blob_key)
            await db.delete(sample)
            removed += 1
        audit.record(
            db,
            action="biometric.purged",
            target_type="biometric_enrollment",
            target_id=enrollment_id,
            user_id=enrollment.user_id,
            actor_id=None,
            meta={"files": removed},
        )
        await db.commit()
