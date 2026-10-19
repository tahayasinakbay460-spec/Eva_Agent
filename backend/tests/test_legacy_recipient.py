"""Miras alıcı deneyimi (adım 8) ve iptal (adım 9): erişim, dondurulmuş sürüm, alıcıların
birbirinden ve sahipten ayrılığı, sahibin ses/yüzüyle görüşme, iptalin anında etkisi."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from app.database import utcnow
from app.models.biometric import AuditLog, Consent
from app.models.call import CallSession
from app.models.job import Job
from app.models.legacy import LegacyAccess, PersonaVersion
from app.models.memory import Memory
from app.models.persona import Persona
from app.models.user import User
from app.persona.compiler import PersonaCompiler
from app.persona.eva import EVA_DEFINITION
from app.persona.types import PersonaDefinition, RelationshipState
from app.providers.base import LLMEvent, LLMRequest, StreamEnd, TextDelta
from app.services.chat_service import ConversationNotFoundError
from app.services.legacy_grant_service import CONSENT_VERSION
from app.services.legacy_service import LegacyNotReadyError
from app.services.voice_service import CallTurns
from app.worker.runner import drain
from tests.conftest import login
from tests.test_legacy_grants import _owner_ready, _redeem, _send
from tests.test_legacy_persona import DRAFT, _session, _step_up
from tests.test_voice import LK

RECIPIENT_FACT = {
    "action": "add",
    "kind": "fact",
    "content": "Elif babasını çok özlüyor.",
    "people": [],
    "importance": 0.8,
    "sensitive": False,
}


class CapturingLLM:
    """Sohbete "tamam" der ve isteği saklar; anı çıkarma isteğine hazır JSON döner."""

    name = "capturing"

    def __init__(self) -> None:
        self.chat_requests: list[LLMRequest] = []
        self.extraction_reply = json.dumps({"memories": [RECIPIENT_FACT]}, ensure_ascii=False)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        if "long-term memory" in request.system[0].text:
            yield TextDelta(self.extraction_reply)
        else:
            self.chat_requests.append(request)
            yield TextDelta("tamam evlat")
        yield StreamEnd(stop_reason="end_turn")

    def last_system(self) -> str:
        return "\n".join(b.text for b in self.chat_requests[-1].system)


@pytest.fixture
def llm(app: FastAPI) -> CapturingLLM:
    provider = CapturingLLM()
    app.state.registry.register_llm("mock", provider)
    return provider


def _voice_on(app: FastAPI) -> None:
    settings = app.state.settings
    settings.livekit_url = LK["livekit_url"]
    settings.livekit_api_key = LK["livekit_api_key"]
    settings.livekit_api_secret = SecretStr(LK["livekit_api_secret"])


async def _shared(
    app: FastAPI, client: httpx.AsyncClient
) -> tuple[dict[str, str], dict[str, str], str, str]:
    """Sahip Miras'ını yayınlar, Elif anahtarla açar. (sahip, alıcı, persona_id, grant_id)"""
    owner = await _owner_ready(app, client)
    created = await _send(client, owner)
    recipient = await login(client, "elif")
    r = await _redeem(app, client, recipient, created["key"])
    assert r.status_code == 200, r.text
    return owner, recipient, r.json()["persona_id"], created["id"]


async def _conversation(client: httpx.AsyncClient, headers: dict[str, str], pid: str) -> str:
    r = await client.post("/chat/conversations", headers=headers, json={"persona_id": pid})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _say(
    client: httpx.AsyncClient, headers: dict[str, str], conv: str, text: str
) -> httpx.Response:
    return await client.post(
        f"/chat/conversations/{conv}/messages",
        headers=headers,
        json={"content": text, "idempotency_key": uuid.uuid4().hex},
    )


async def _run_jobs_now(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        for job in (await db.execute(select(Job).where(Job.status == "pending"))).scalars():
            job.run_at = utcnow()
        await db.commit()
    await drain(app.state.worker_context)


# --- erişim ve sürüm ---------------------------------------------------------------------


async def test_recipient_sees_and_talks_to_the_shared_legacy(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    _owner, elif_, pid, _ = await _shared(app, client)
    shared = (await client.get("/legacy/shared", headers=elif_)).json()
    assert [(s["persona_id"], s["status"]) for s in shared] == [(pid, "active")]
    assert shared[0]["owner_name"]
    assert pid in {p["id"] for p in (await client.get("/personas", headers=elif_)).json()}

    conv = await _conversation(client, elif_, pid)
    r = await _say(client, elif_, conv, "Baba, seni özledim.")
    assert r.status_code == 200 and "tamam evlat" in r.text
    system = llm.last_system()
    assert str(DRAFT["identity"]) in system
    assert "Kızıma parkta bisiklet sürmeyi öğrettim." in system, "canon memories are in"
    assert "share your legacy" in system and "just met" not in system


async def test_recipient_talks_to_the_published_version_not_the_live_draft(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    owner, elif_, pid, _ = await _shared(app, client)
    await client.put("/legacy/persona", headers=owner, json={**DRAFT, "identity": "TASLAK-2"})
    conv = await _conversation(client, elif_, pid)
    await _say(client, elif_, conv, "Merhaba baba")
    assert str(DRAFT["identity"]) in llm.last_system()
    assert "TASLAK-2" not in llm.last_system()
    # Sahip yeniden yayınlayınca alıcı yeni sürüme geçer.
    await _step_up(app, owner)
    assert (await client.post("/legacy/persona/publish", headers=owner)).json()["version"] == 2
    await _say(client, elif_, conv, "Yine ben")
    assert "TASLAK-2" in llm.last_system()


async def test_recipient_conversations_never_change_the_base_persona(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    owner, elif_, pid, _ = await _shared(app, client)
    async with app.state.session_factory() as db:
        before_persona = (await db.get(Persona, uuid.UUID(pid))).definition
        before_versions = [v.definition for v in (await db.scalars(select(PersonaVersion)))]
        owner_id = (await db.get(Persona, uuid.UUID(pid))).owner_id

    conv = await _conversation(client, elif_, pid)
    await _say(client, elif_, conv, "Baba seni çok özlüyorum, keşke burada olsan.")
    await _run_jobs_now(app)

    async with app.state.session_factory() as db:
        assert (await db.get(Persona, uuid.UUID(pid))).definition == before_persona
        assert [v.definition for v in (await db.scalars(select(PersonaVersion)))] == before_versions
        memories = (
            await db.scalars(select(Memory).where(Memory.persona_id == uuid.UUID(pid)))
        ).all()
    # Çıkarılan anı alıcıya ait; sahibin hiçbir anısı değişmedi.
    assert [(m.content, m.source) for m in memories] == [("Elif babasını çok özlüyor.", "auto")]
    assert all(m.user_id != owner_id for m in memories)
    owner_memories = (await client.get("/memories", headers=owner)).json()
    assert "Elif babasını çok özlüyor." not in {m["content"] for m in owner_memories}


async def test_recipient_family_memories_are_separate_and_reach_only_their_prompt(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    owner, elif_, pid, _ = await _shared(app, client)
    r = await client.post(
        "/memories",
        headers=elif_,
        json={"persona_id": pid, "content": "Babamla her bayram baklava yapardık."},
    )
    assert r.status_code == 201 and r.json()["source"] == "recipient_added"
    conv = await _conversation(client, elif_, pid)
    await _say(client, elif_, conv, "Baba bayramda baklava yapalım mı?")
    assert "baklava yapardık" in llm.last_system()
    # Sahibin kendi listesinde görünmez; Miras sürümüne girmez.
    assert "baklava" not in json.dumps((await client.get("/memories", headers=owner)).json())
    async with app.state.session_factory() as db:
        versions = (await db.scalars(select(PersonaVersion))).all()
    assert all("baklava" not in json.dumps(v.definition) for v in versions)


async def test_recipients_are_isolated_from_each_other(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    owner, elif_, pid, _ = await _shared(app, client)
    created = await _send(client, owner, "murat@ornek.com")
    murat = await login(client, "murat")
    assert (await _redeem(app, client, murat, created["key"])).status_code == 200

    await client.post(
        "/memories", headers=elif_, json={"persona_id": pid, "content": "Elif'in sırrı."}
    )
    elif_conv = await _conversation(client, elif_, pid)
    await _say(client, elif_, elif_conv, "Bu sadece Elif'in mesajı")

    # Murat, Elif'in konuşmasını ve anısını göremez.
    r = await client.get(f"/chat/conversations/{elif_conv}/messages", headers=murat)
    assert r.status_code == 404
    murat_conv = await _conversation(client, murat, pid)
    await _say(client, murat, murat_conv, "Merhaba baba")
    system = llm.last_system()
    assert "Elif'in sırrı" not in system and "Bu sadece Elif'in mesajı" not in system
    memories = (await client.get(f"/memories?persona_id={pid}", headers=murat)).json()
    assert memories == []


async def test_strangers_cannot_reach_a_shared_legacy(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    _voice_on(app)
    _owner, elif_, pid, _ = await _shared(app, client)
    stranger = await login(client, "yabanci")
    assert (
        await client.post("/chat/conversations", headers=stranger, json={"persona_id": pid})
    ).status_code == 404
    assert (
        await client.post("/voice/calls", headers=stranger, json={"persona_id": pid})
    ).status_code == 404
    assert (
        await client.post("/memories", headers=stranger, json={"persona_id": pid, "content": "x"})
    ).status_code == 404
    assert (await client.get("/legacy/shared", headers=stranger)).json() == []
    access_id = (await client.get("/legacy/shared", headers=elif_)).json()[0]["access_id"]
    assert (
        await client.post(f"/legacy/shared/{access_id}/archive", headers=stranger)
    ).status_code == 404
    assert (await client.delete(f"/legacy/shared/{access_id}", headers=stranger)).status_code == 404


# --- sesli / görüntülü ---------------------------------------------------------------------


async def _call_media(app: FastAPI, call_id: str) -> Any:
    async with app.state.session_factory() as db:
        return await CallTurns(app.state.chat_service).call_media(
            db,
            uuid.UUID(call_id),
            media_config=app.state.settings.media_config,
            tts_provider="mock",
            avatar_provider="mock",
            avatar_accepts_image=False,
            store=app.state.store,
        )


async def _still_allowed(app: FastAPI, call_id: str) -> bool:
    async with app.state.session_factory() as db:
        allowed: bool = await CallTurns(app.state.chat_service).media_still_allowed(
            db, uuid.UUID(call_id)
        )
        return allowed


async def test_recipient_video_call_uses_the_owners_voice_and_face(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    _voice_on(app)
    _owner, elif_, pid, _ = await _shared(app, client)
    r = await client.post("/voice/calls", headers=elif_, json={"persona_id": pid, "mode": "video"})
    assert r.status_code == 201, r.text
    call_id = r.json()["call_id"]
    media = await _call_media(app, call_id)
    assert (media.voice_id, media.avatar_id) == ("mock-voice", "mock-face")
    assert await _still_allowed(app, call_id)


# --- iptal (adım 9) ------------------------------------------------------------------------


async def test_owner_revoke_stops_chat_and_calls_immediately(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    _voice_on(app)
    owner, elif_, pid, grant_id = await _shared(app, client)
    conv = await _conversation(client, elif_, pid)
    assert (await _say(client, elif_, conv, "Merhaba")).status_code == 200
    r = await client.post("/voice/calls", headers=elif_, json={"persona_id": pid})
    call_id = r.json()["call_id"]

    # İptal adım-yukarı ister; başkası iptal edemez.
    stranger = await login(client, "yabanci")
    await _step_up(app, stranger)
    assert (
        await client.post(f"/legacy/grants/{grant_id}/revoke", headers=stranger)
    ).status_code == 404
    owner_fresh = await login(client, "ahmet")
    r = await client.post(f"/legacy/grants/{grant_id}/revoke", headers=owner_fresh)
    assert r.status_code == 403
    await _step_up(app, owner)
    r = await client.post(f"/legacy/grants/{grant_id}/revoke", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "revoked"

    # Etkisi anında: yazışma, yeni sohbet, görüşme, anı ekleme kapalı; açık görüşme bitti.
    assert (await _say(client, elif_, conv, "Orada mısın?")).status_code == 404
    assert (
        await client.post("/chat/conversations", headers=elif_, json={"persona_id": pid})
    ).status_code == 404
    assert (
        await client.post("/voice/calls", headers=elif_, json={"persona_id": pid})
    ).status_code == 404
    assert not await _still_allowed(app, call_id)
    async with app.state.session_factory() as db:
        call = await db.get(CallSession, uuid.UUID(call_id))
        assert call is not None and (call.status, call.end_reason) == ("ended", "legacy_revoked")
        actions = (await db.scalars(select(AuditLog.action))).all()
    assert "legacy.revoked" in actions
    shared = (await client.get("/legacy/shared", headers=elif_)).json()
    assert shared[0]["status"] == "revoked" and shared[0]["ended_at"]
    assert pid not in {p["id"] for p in (await client.get("/personas", headers=elif_)).json()}
    # Tekrar iptal etmek zararsız.
    r = await client.post(f"/legacy/grants/{grant_id}/revoke", headers=owner)
    assert r.status_code == 200


async def test_revoking_an_unused_key_makes_it_worthless(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _owner_ready(app, client)
    created = await _send(client, owner)
    r = await client.post(f"/legacy/grants/{created['id']}/revoke", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    elif_ = await login(client, "elif")
    r = await client.post("/legacy/redeem", headers=elif_, json={"key": created["key"]})
    assert r.status_code == 400 and r.json() == {"detail": "invalid_or_expired"}


async def test_owner_withdrawing_voice_or_face_consent_stops_the_legacy(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    _voice_on(app)
    owner, elif_, pid, _ = await _shared(app, client)
    conv = await _conversation(client, elif_, pid)
    r = await client.post("/voice/calls", headers=elif_, json={"persona_id": pid, "mode": "video"})
    call_id = r.json()["call_id"]
    owner_id = (await _session(app, owner)).user_id
    async with app.state.session_factory() as db:
        consent = (
            await db.scalars(
                select(Consent).where(Consent.user_id == owner_id, Consent.purpose == "face_avatar")
            )
        ).one()
        consent.status = "revoked"
        await db.commit()
    assert not await _still_allowed(app, call_id)
    r = await _say(client, elif_, conv, "Baba?")
    assert r.status_code == 409 and r.json()["detail"] == "legacy_media_unavailable"
    r = await client.post("/chat/conversations", headers=elif_, json={"persona_id": pid})
    assert r.status_code == 409 and r.json()["detail"] == "legacy_media_unavailable"


# --- alıcının vedası: arşiv ve silme -------------------------------------------------------


async def test_recipient_can_archive_then_delete_their_side(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    owner, elif_, pid, _ = await _shared(app, client)
    await client.post("/memories", headers=elif_, json={"persona_id": pid, "content": "Aile anısı"})
    conv = await _conversation(client, elif_, pid)
    await _say(client, elif_, conv, "Hoşça kal baba")
    access_id = (await client.get("/legacy/shared", headers=elif_)).json()[0]["access_id"]

    r = await client.post(f"/legacy/shared/{access_id}/archive", headers=elif_)
    assert r.status_code == 200 and r.json()["status"] == "archived"
    assert (await _say(client, elif_, conv, "Bir şey daha")).status_code == 404
    # Arşiv geçmişi silmez.
    async with app.state.session_factory() as db:
        mine = (await db.scalars(select(Memory).where(Memory.persona_id == uuid.UUID(pid)))).all()
    assert [m.content for m in mine] == ["Aile anısı"]

    r = await client.delete(f"/legacy/shared/{access_id}", headers=elif_)
    assert r.status_code == 204
    assert (await client.get("/legacy/shared", headers=elif_)).json() == []
    assert (
        await client.get(f"/chat/conversations/{conv}/messages", headers=elif_)
    ).status_code == 404
    async with app.state.session_factory() as db:
        left = (await db.scalars(select(Memory).where(Memory.persona_id == uuid.UUID(pid)))).all()
        assert left == []
        persona = await db.get(Persona, uuid.UUID(pid))
        assert persona is not None, "the owner's legacy itself is untouched"
        access = await db.get(LegacyAccess, uuid.UUID(access_id))
        assert access is not None and access.status == "deleted"
    # Sahibin önizlemesi çalışmaya devam eder.
    own_conv = await _conversation(client, owner, pid)
    assert (await _say(client, owner, own_conv, "Deneme")).status_code == 200


# --- savunma derinliği: kontrol akışın içinde de var ---------------------------------------


async def _revoke(app: FastAPI, client: httpx.AsyncClient, owner: dict[str, str], gid: str) -> None:
    await _step_up(app, owner)
    r = await client.post(f"/legacy/grants/{gid}/revoke", headers=owner)
    assert r.status_code == 200


async def test_revoked_mid_turn_chat_produces_no_reply(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    """Yönlendiricideki ön kontrolden sonra iptal gelse bile (yarış), servis modeli çağırmaz."""
    owner, elif_, pid, gid = await _shared(app, client)
    conv = await _conversation(client, elif_, pid)
    await _revoke(app, client, owner, gid)
    calls_before = len(llm.chat_requests)
    recipient_id = (await _session(app, elif_)).user_id
    async with app.state.session_factory() as db:
        user = await db.get(User, recipient_id)
        assert user is not None
        with pytest.raises(ConversationNotFoundError):
            async for _ in app.state.chat_service.stream_reply(
                db, user, uuid.UUID(conv), "Baba?", uuid.uuid4().hex
            ):
                pass
    assert len(llm.chat_requests) == calls_before


async def test_revoked_mid_call_next_voice_turn_is_refused(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    _voice_on(app)
    owner, elif_, pid, gid = await _shared(app, client)
    r = await client.post("/voice/calls", headers=elif_, json={"persona_id": pid})
    call_id = uuid.UUID(r.json()["call_id"])
    async with app.state.session_factory() as db:
        request = await CallTurns(app.state.chat_service).prepare_reply(
            db, call_id, user_item_id="t1", user_text="Baba?"
        )
    assert "share your legacy" in "\n".join(b.text for b in request.system)
    await _revoke(app, client, owner, gid)
    async with app.state.session_factory() as db:
        with pytest.raises(LegacyNotReadyError):
            await CallTurns(app.state.chat_service).prepare_reply(
                db, call_id, user_item_id="t2", user_text="Orada mısın?"
            )


# --- anı kaynakları ve prompt notu ---------------------------------------------------------


async def test_owner_memories_added_to_the_legacy_are_owner_legacy(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _owner_ready(app, client)
    pid = (await client.get("/legacy/persona", headers=owner)).json()["id"]
    r = await client.post(
        "/memories", headers=owner, json={"persona_id": pid, "content": "Torunlarıma not."}
    )
    assert r.status_code == 201 and r.json()["source"] == "owner_legacy"
    r = await client.post("/memories", headers=owner, json={"content": "EVA anısı"})
    assert r.json()["source"] == "user_added"


def test_compiler_uses_the_legacy_relationship_note() -> None:
    legacy = PersonaDefinition(
        name="Baba", kind="legacy", identity="x", personality="y", speaking_style="z"
    )
    prompt = PersonaCompiler().compile(legacy, relationship=RelationshipState())
    note = prompt.system[-1].text
    assert "share your legacy" in note and "just met" not in note
    eva = PersonaCompiler().compile(EVA_DEFINITION, relationship=RelationshipState())
    assert "just met" in eva.system[-1].text


# --- yeniden anahtar (yaşarken paylaş) ---------------------------------------------------


async def test_owner_can_rekey_someone_who_left_and_they_get_a_single_entry(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    owner, elif_, pid, _ = await _shared(app, client)
    app.state.settings.legacy_max_grants = 1
    access_id = (await client.get("/legacy/shared", headers=elif_)).json()[0]["access_id"]

    # Elif hâlâ açıkken sınır dolu.
    body = {
        "recipient_email": "baska@ornek.com",
        "consent_accepted": True,
        "consent_text_version": CONSENT_VERSION,
    }
    r = await client.post("/legacy/grants", headers=owner, json=body)
    assert r.status_code == 409 and r.json()["detail"] == "legacy_grant_limit"

    # Elif kaldırınca yer açılır; sahip ona yeniden anahtar gönderebilir.
    assert (
        await client.post(f"/legacy/shared/{access_id}/archive", headers=elif_)
    ).status_code == 200
    created = await _send(client, owner)
    r = await _redeem(app, client, elif_, created["key"])
    assert r.status_code == 200
    shared = (await client.get("/legacy/shared", headers=elif_)).json()
    assert [(s["persona_id"], s["status"]) for s in shared] == [(pid, "active")]
    conv = await _conversation(client, elif_, pid)
    assert (await _say(client, elif_, conv, "Yeniden merhaba baba")).status_code == 200


async def test_owner_can_rekey_after_closing_access(
    app: FastAPI, client: httpx.AsyncClient, llm: CapturingLLM
) -> None:
    owner, elif_, _pid, grant_id = await _shared(app, client)
    await _step_up(app, owner)
    assert (
        await client.post(f"/legacy/grants/{grant_id}/revoke", headers=owner)
    ).status_code == 200
    created = await _send(client, owner)
    assert (await _redeem(app, client, elif_, created["key"])).status_code == 200
    shared = (await client.get("/legacy/shared", headers=elif_)).json()
    assert [s["status"] for s in shared] == ["active"]
