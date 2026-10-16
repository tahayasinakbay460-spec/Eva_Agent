"""Faz 1 çıkış kriteri: "Bunu unut" uçtan uca gerçekten unutturur (CLAUDE.md §6.4, §14).

Bir anı her yere yayıldıktan sonra (veritabanı, vektör, sohbet prompt'u) unutturulur ve
hiçbir yerde kalmadığı, sonradan da geri gelmediği kontrol edilir.
"""

import json
import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select

from app.database import utcnow
from app.models.job import Job
from app.models.memory import Memory, MemoryEmbedding
from app.providers.base import LLMEvent, LLMRequest, StreamEnd, TextDelta
from app.worker.runner import WorkerContext, drain

SECRET = "Eski sevgilimin adı Deniz."


class _Provider:
    """Sohbette "tamam" der ve istekleri saklar. Anı çıkarmada SECRET'i sadece orijinal
    mesajı görürse önerir: eski mesajlar tekrar işlenirse anı geri gelir ve test yakalar.
    """

    name = "spy"

    def __init__(self) -> None:
        self.chat_requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        if "long-term memory" in request.system[0].text:
            conversation = request.messages[0].content.split("<conversation>")[1]
            memories = []
            if "Eski sevgilimin adı Deniz" in conversation:
                memories.append(
                    {"action": "add", "kind": "fact", "content": SECRET, "importance": 0.9}
                )
            yield TextDelta(json.dumps({"memories": memories}, ensure_ascii=False))
        else:
            self.chat_requests.append(request)
            yield TextDelta("tamam")
        yield StreamEnd(stop_reason="end_turn")


async def _drain_now(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        for job in (await db.execute(select(Job).where(Job.status == "pending"))).scalars():
            job.run_at = utcnow()
        await db.commit()
    ctx: WorkerContext = app.state.worker_context
    await drain(ctx)


async def _count(app: FastAPI, model: type[Memory] | type[MemoryEmbedding]) -> int:
    async with app.state.session_factory() as db:
        return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def test_forget_removes_a_memory_everywhere_for_good(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = _Provider()
    app.state.registry.register_llm("mock", provider)
    conv = (await client.post("/chat/conversations", json={}, headers=auth_headers)).json()["id"]

    async def say(text: str) -> None:
        r = await client.post(
            f"/chat/conversations/{conv}/messages",
            json={"content": text, "idempotency_key": uuid.uuid4().hex},
            headers=auth_headers,
        )
        assert r.status_code == 200

    # 1) Kullanıcı anlatır, işçi anıyı çıkarır ve vektörünü üretir.
    await say("Eski sevgilimin adı Deniz, artık konuşmuyoruz.")
    await _drain_now(app)
    (memory,) = (await client.get("/memories", headers=auth_headers)).json()
    assert memory["content"] == SECRET and memory["source"] == "auto"
    assert await _count(app, MemoryEmbedding) == 1

    # 2) EVA artık biliyor: sohbette prompt'a giriyor.
    await say("Deniz'i hatırlıyor musun?")
    assert SECRET in "\n".join(b.text for b in provider.chat_requests[-1].system)

    # 3) Kullanıcı "EVA ne biliyor" ekranından unutturur.
    r = await client.delete(f"/memories/{memory['id']}", headers=auth_headers)
    assert r.status_code == 204

    # 4) Hiçbir yerde kalmadı: tablo, vektör, liste, sohbet prompt'u.
    assert await _count(app, Memory) == 0
    assert await _count(app, MemoryEmbedding) == 0
    assert (await client.get("/memories", headers=auth_headers)).json() == []
    await say("Deniz'i hatırlıyor musun?")
    assert SECRET not in "\n".join(b.text for b in provider.chat_requests[-1].system)

    # 5) Sonraki arka plan işleri onu eski mesajlardan geri getirmez: çıkarma sadece
    #    henüz işlenmemiş (yeni) mesajlara bakar.
    await _drain_now(app)
    assert await _count(app, Memory) == 0, "unutulan anı geri gelmemeli"
