"""Arka plan işlerinin kendisi. Her işleyici tekrar çalıştırılabilir (idempotent) olmalı:
işçi çökerse aynı iş ikinci kez gelebilir.
"""

import uuid
from typing import Any

from sqlalchemy import delete

from app.models.memory import Memory, MemoryEmbedding
from app.services import memory_extraction
from app.worker.jobs import EMBED_MEMORY, EXTRACT_MEMORIES
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
