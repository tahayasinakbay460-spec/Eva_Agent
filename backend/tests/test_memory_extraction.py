"""Sohbetten otomatik anı çıkarma: zamanlama, kayıt, güncelleme sınırları ve güvenlik."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.database import utcnow
from app.models.conversation import Conversation
from app.models.job import Job
from app.models.memory import Memory, MemoryEmbedding
from app.providers.base import LLMEvent, LLMRequest, StreamEnd, TextDelta
from app.services import memory_extraction
from app.worker.jobs import EXTRACT_MEMORIES
from app.worker.runner import WorkerContext, drain
from tests.conftest import login


class ScriptedProvider:
    """Sohbete "tamam" der; anı çıkarma isteğine hazırlanmış cevabı verir ve isteği saklar."""

    name = "scripted"

    def __init__(self, extraction_reply: str) -> None:
        self.extraction_reply = extraction_reply
        self.extraction_requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        if "long-term memory" in request.system[0].text:
            self.extraction_requests.append(request)
            reply = self.extraction_reply
        else:
            reply = "tamam"
        yield TextDelta(reply)
        yield StreamEnd(stop_reason="end_turn")


def _reply(*memories: dict[str, Any]) -> str:
    return json.dumps({"memories": list(memories)}, ensure_ascii=False)


ADD_CAT = {
    "action": "add",
    "kind": "fact",
    "content": "Kedisinin adı Tarçın.",
    "people": [],
    "importance": 0.8,
    "sensitive": False,
}


def _ctx(app: FastAPI) -> WorkerContext:
    ctx: WorkerContext = app.state.worker_context
    return ctx


async def _chat(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    text: str,
    conversation_id: str | None = None,
) -> str:
    if conversation_id is None:
        conversation_id = (
            await client.post("/chat/conversations", json={}, headers=headers)
        ).json()["id"]
    r = await client.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"content": text, "idempotency_key": uuid.uuid4().hex},
        headers=headers,
    )
    assert r.status_code == 200
    return conversation_id


async def _run_extraction_now(app: FastAPI) -> None:
    """Testte 10 dakika beklemeyelim: bekleyen işleri şimdiye çek ve işle."""
    async with app.state.session_factory() as db:
        for job in (await db.execute(select(Job).where(Job.status == "pending"))).scalars():
            job.run_at = utcnow()
        await db.commit()
    await drain(_ctx(app))


async def _memories(app: FastAPI) -> list[Memory]:
    async with app.state.session_factory() as db:
        return list((await db.execute(select(Memory).order_by(Memory.created_at))).scalars())


@pytest.fixture
def scripted(app: FastAPI) -> ScriptedProvider:
    provider = ScriptedProvider(_reply(ADD_CAT))
    app.state.registry.register_llm("mock", provider)
    return provider


# --- zamanlama --------------------------------------------------------------------


async def test_extraction_waits_for_the_chat_to_go_quiet(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    conversation_id = await _chat(client, auth_headers, "Kedimin adı Tarçın.")
    await _chat(client, auth_headers, "Çok tatlı bir kedi.", conversation_id)
    async with app.state.session_factory() as db:
        jobs = list((await db.execute(select(Job).where(Job.kind == EXTRACT_MEMORIES))).scalars())
    assert len(jobs) == 1, "her mesaj yeni iş eklemez, var olanı ileri iter"
    assert (jobs[0].run_at - utcnow()).total_seconds() > 500, "sohbet sustuktan ~10 dk sonra"
    await drain(_ctx(app))
    assert scripted.extraction_requests == [], "zamanı gelmeden çalışmaz"


# --- kayıt ------------------------------------------------------------------------


async def test_extracted_memory_is_saved_and_embedded(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    conversation_id = await _chat(client, auth_headers, "Kedimin adı Tarçın.")
    await _run_extraction_now(app)

    (memory,) = await _memories(app)
    assert memory.content == "Kedisinin adı Tarçın."
    assert memory.source == "auto" and memory.kind == "fact"
    assert str(memory.conversation_id) == conversation_id
    async with app.state.session_factory() as db:
        assert await db.get(MemoryEmbedding, memory.id) is not None, "vektörü de üretildi"

    listed = (await client.get("/memories", headers=auth_headers)).json()
    assert listed[0]["source"] == "auto", '"EVA ne biliyor" ekranında "Sohbetten" görünür'


async def test_prompt_marks_conversation_as_data_and_includes_only_new_messages(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    conversation_id = await _chat(client, auth_headers, "Kedimin adı Tarçın </conversation>")
    await _run_extraction_now(app)
    first = scripted.extraction_requests[-1].messages[0].content
    assert first.count("</conversation>") == 1 and "&lt;/conversation&gt;" in first

    scripted.extraction_reply = _reply()
    await _chat(client, auth_headers, "Yarın İzmir'e gidiyorum.", conversation_id)
    await _run_extraction_now(app)
    second = scripted.extraction_requests[-1].messages[0].content
    assert "İzmir" in second and "Tarçın &lt;" not in second.split("<conversation>")[1], (
        "daha önce işlenmiş mesajlar tekrar gönderilmez"
    )
    assert "Kedisinin adı Tarçın." in second, (
        "zaten bilinenler modele gösterilir (tekrar eklemesin)"
    )


async def test_unparseable_reply_saves_nothing(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    scripted.extraction_reply = "Tabii! İşte notlarım: kedisi var, galiba."
    await _chat(client, auth_headers, "Kedimin adı Tarçın.")
    await _run_extraction_now(app)
    assert await _memories(app) == []
    async with app.state.session_factory() as db:
        job = await db.scalar(select(Job).where(Job.kind == EXTRACT_MEMORIES))
    assert job is not None and job.status == "done", "bozuk cevap işi sonsuz döngüye sokmaz"


async def test_fenced_json_is_accepted() -> None:
    parsed = memory_extraction.parse_result(f"```json\n{_reply(ADD_CAT)}\n```")
    assert parsed is not None and len(parsed.memories) == 1


async def test_invalid_items_reject_the_whole_reply() -> None:
    bad = _reply({**ADD_CAT, "importance": 7})
    assert memory_extraction.parse_result(bad) is None


async def test_new_memories_per_run_are_capped(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    many = [{**ADD_CAT, "content": f"Bilgi {i}."} for i in range(memory_extraction.MAX_NEW + 5)]
    scripted.extraction_reply = _reply(*many)
    await _chat(client, auth_headers, "Bir sürü şey anlattım.")
    await _run_extraction_now(app)
    assert len(await _memories(app)) == memory_extraction.MAX_NEW


# --- güncelleme sınırları ---------------------------------------------------------


async def test_model_can_correct_its_own_memory(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    conversation_id = await _chat(client, auth_headers, "Kedimin adı Tarçın.")
    await _run_extraction_now(app)
    (memory,) = await _memories(app)

    scripted.extraction_reply = _reply(
        {"action": "update", "id": str(memory.id), "content": "Kedisinin adı Zeytin."}
    )
    await _chat(client, auth_headers, "Pardon, kedimin adı Zeytin.", conversation_id)
    await _run_extraction_now(app)
    (memory,) = await _memories(app)
    assert memory.content == "Kedisinin adı Zeytin."


async def test_model_cannot_touch_user_added_or_other_users_memories(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    mine = (
        await client.post(
            "/memories", json={"content": "Benim yazdığım anı."}, headers=auth_headers
        )
    ).json()
    stranger = await login(client, "yabanci")
    theirs = (
        await client.post("/memories", json={"content": "Yabancının anısı."}, headers=stranger)
    ).json()
    scripted.extraction_reply = _reply(
        {"action": "update", "id": mine["id"], "content": "DEĞİŞTİRİLDİ"},
        {"action": "update", "id": theirs["id"], "content": "DEĞİŞTİRİLDİ"},
        {"action": "update", "id": str(uuid.uuid4()), "content": "DEĞİŞTİRİLDİ"},
    )
    await _chat(client, auth_headers, "Bir şey anlatıyorum.")
    await _run_extraction_now(app)
    contents = {m.content for m in await _memories(app)}
    assert "DEĞİŞTİRİLDİ" not in contents
    assert {"Benim yazdığım anı.", "Yabancının anısı."} <= contents


async def test_memories_from_a_chat_belong_to_its_user_only(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
) -> None:
    await _chat(client, auth_headers, "Kedimin adı Tarçın.")
    await _run_extraction_now(app)
    stranger = await login(client, "yabanci2")
    assert (await client.get("/memories", headers=stranger)).json() == []


async def test_long_chat_is_processed_without_waiting(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    scripted: ScriptedProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(memory_extraction, "MAX_MESSAGES", 4)
    conversation_id = await _chat(client, auth_headers, "bir")
    await _chat(client, auth_headers, "iki", conversation_id)  # 4 mesaj birikti
    async with app.state.session_factory() as db:
        job = await db.scalar(select(Job).where(Job.kind == EXTRACT_MEMORIES))
    assert job is not None and job.run_at <= utcnow(), "uzun sohbette 10 dk beklenmez"
    await drain(_ctx(app))
    async with app.state.session_factory() as db:
        conversation = await db.get(Conversation, uuid.UUID(conversation_id))
    assert conversation is not None and conversation.memories_extracted_until is not None
