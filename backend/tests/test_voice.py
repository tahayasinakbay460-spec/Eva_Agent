"""Sesli/görüntülü görüşme (Faz 2): görüşme açma, LiveKit token'ı, tur kaydı, gecikme panosu."""

import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.database import utcnow
from app.models.call import CallSession, TurnLatency
from app.models.conversation import Message
from app.models.job import Job
from app.services.voice_service import CALL_OPENING_CUE, CallNotFoundError, CallTurns, TurnTimings
from tests.conftest import build_app, login, make_settings

LK = {
    "livekit_url": "ws://localhost:7880",
    "livekit_api_key": "devkey",
    "livekit_api_secret": "secret-secret-secret-secret-secret",
}


@pytest.fixture
async def voice_app(tmp_path: Path) -> Any:
    app = await build_app(make_settings(tmp_path, **LK))
    yield app
    await app.state.engine.dispose()


@pytest.fixture
async def vclient(voice_app: FastAPI) -> Any:
    transport = httpx.ASGITransport(app=voice_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _start(client: httpx.AsyncClient, headers: dict[str, str], **body: Any) -> Any:
    r = await client.post("/voice/calls", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _claims(token: str) -> dict[str, Any]:
    """Token'ı bizim gizli anahtarımızla doğrulayıp içeriğini açar (imza yanlışsa hata)."""
    claims: dict[str, Any] = jwt.decode(token, LK["livekit_api_secret"], algorithms=["HS256"])
    return claims


def _turns(app: FastAPI) -> CallTurns:
    return CallTurns(app.state.chat_service)


# --- görüşme açma ----------------------------------------------------------------


async def test_voice_not_configured(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/voice/calls", headers=auth_headers, json={})
    assert r.status_code == 503
    assert r.json() == {"detail": "voice_not_configured"}


async def test_calls_require_login(vclient: httpx.AsyncClient) -> None:
    assert (await vclient.post("/voice/calls", json={})).status_code == 401
    assert (await vclient.get("/voice/latency")).status_code == 401


async def test_token_is_short_lived_room_bound_and_mic_only(vclient: httpx.AsyncClient) -> None:
    headers = await login(vclient)
    body = await _start(vclient, headers)
    assert body["livekit_url"] == "ws://localhost:7880"
    assert body["max_duration_s"] == 1800 and body["idle_timeout_s"] == 60

    claims = _claims(body["token"])
    grants = claims["video"]
    assert grants["roomJoin"] and grants["room"].startswith("eva-")
    assert grants["canPublishSources"] == ["microphone"], "no camera or screen sharing"
    assert grants["canPublishData"] is False
    assert grants["canUpdateOwnMetadata"] is False, "client must not tamper with its identity"
    assert not grants.get("roomAdmin") and not grants.get("roomCreate")
    assert claims["sub"].startswith("user-")
    assert claims["exp"] - claims["nbf"] <= 120, "short-lived"

    (dispatch,) = claims["roomConfig"]["agents"]
    assert dispatch["agentName"] == "eva-voice"
    assert json.loads(dispatch["metadata"]) == {"call_id": body["call_id"]}


async def test_call_continues_the_text_conversation(vclient: httpx.AsyncClient) -> None:
    """Metinden sese geçince konuşma kaldığı yerden sürer (§5.3)."""
    headers = await login(vclient)
    r = await vclient.post("/chat/conversations", headers=headers, json={})
    text_conversation = r.json()["id"]
    body = await _start(vclient, headers)
    assert body["conversation_id"] == text_conversation


async def test_unknown_persona_is_404(vclient: httpx.AsyncClient) -> None:
    headers = await login(vclient)
    r = await vclient.post("/voice/calls", headers=headers, json={"persona_id": str(uuid.uuid4())})
    assert r.status_code == 404


async def test_new_call_replaces_an_open_one(
    voice_app: FastAPI, vclient: httpx.AsyncClient
) -> None:
    headers = await login(vclient)
    first = await _start(vclient, headers)
    await _start(vclient, headers)
    r = await vclient.get(f"/voice/calls/{first['call_id']}", headers=headers)
    assert r.json()["status"] == "ended"
    assert r.json()["end_reason"] == "replaced"


async def test_users_cannot_see_or_end_each_others_calls(vclient: httpx.AsyncClient) -> None:
    alice = await login(vclient, "alice")
    bob = await login(vclient, "bob")
    call = await _start(vclient, alice)
    assert (await vclient.get(f"/voice/calls/{call['call_id']}", headers=bob)).status_code == 404
    r = await vclient.post(f"/voice/calls/{call['call_id']}/end", headers=bob)
    assert r.status_code == 404
    r = await vclient.get(f"/voice/calls/{call['call_id']}", headers=alice)
    assert r.json()["status"] == "created"


async def test_end_call_is_idempotent_and_schedules_memory_extraction(
    voice_app: FastAPI, vclient: httpx.AsyncClient
) -> None:
    headers = await login(vclient)
    call = await _start(vclient, headers)
    for _ in range(2):
        r = await vclient.post(f"/voice/calls/{call['call_id']}/end", headers=headers)
        assert r.status_code == 204
    async with voice_app.state.session_factory() as db:
        jobs = (await db.execute(select(Job).where(Job.kind == "extract_memories"))).scalars()
        assert len(list(jobs)) == 1


async def test_video_quota(voice_app: FastAPI, vclient: httpx.AsyncClient) -> None:
    headers = await login(vclient)
    first = await _start(vclient, headers, mode="video")
    assert first["max_duration_s"] == 600

    # Bugün 25 dakika görüntülü görüşme yapılmış gibi yap: kalan 5 dk.
    async with voice_app.state.session_factory() as db:
        call = await db.get(CallSession, uuid.UUID(first["call_id"]))
        assert call is not None
        now = utcnow()
        call.started_at = max(now - timedelta(minutes=25), now.replace(hour=0, minute=0))
        call.ended_at = call.started_at + timedelta(minutes=25)
        call.status = "ended"
        await db.commit()
        used = (call.ended_at - call.started_at).total_seconds()
    second = await _start(vclient, headers, mode="video")
    assert second["max_duration_s"] <= 1800 - used + 1

    async with voice_app.state.session_factory() as db:
        call = await db.get(CallSession, uuid.UUID(second["call_id"]))
        assert call is not None
        call.started_at = utcnow() - timedelta(seconds=call.max_duration_s)
        call.ended_at = utcnow()
        call.status = "ended"
        await db.commit()
    r = await vclient.post("/voice/calls", headers=headers, json={"mode": "video"})
    if used >= 1500:  # gece yarısına yakın koşarsa kota günü değişmiş olabilir
        assert r.status_code == 429
        assert r.json() == {"detail": "video_quota_exceeded"}
    # Sesli görüşme avatar kotasına takılmaz.
    assert (await vclient.post("/voice/calls", headers=headers, json={})).status_code == 201


# --- ajan tarafı: turlar ------------------------------------------------------------


async def test_turns_save_user_speech_once_and_build_a_voice_prompt(
    voice_app: FastAPI, vclient: httpx.AsyncClient
) -> None:
    headers = await login(vclient)
    call = await _start(vclient, headers)
    call_id = uuid.UUID(call["call_id"])
    turns = _turns(voice_app)
    async with voice_app.state.session_factory() as db:
        opened = await turns.open(db, call_id)
        assert opened.status == "active" and opened.started_at is not None

        for _ in range(2):  # aynı tur iki kez gelirse bir kez kaydedilir
            request = await turns.prepare_reply(
                db, call_id, user_item_id="item_1", user_text="Bugün çok yoruldum"
            )
        assert request.model == "gpt-6-luna"
        assert request.max_tokens == 400, "realtime feature config is used"
        assert any("live voice call" in b.text for b in request.system)
        assert request.messages[-1].content == "Bugün çok yoruldum"
        assert sum(m.content == "Bugün çok yoruldum" for m in request.messages) == 1

        messages = (await db.execute(select(Message))).scalars().all()
        assert [(m.role, m.channel, m.content) for m in messages] == [
            ("user", "voice", "Bugün çok yoruldum")
        ]


async def test_opening_greeting_is_not_saved(
    voice_app: FastAPI, vclient: httpx.AsyncClient
) -> None:
    headers = await login(vclient)
    call_id = uuid.UUID((await _start(vclient, headers))["call_id"])
    turns = _turns(voice_app)
    async with voice_app.state.session_factory() as db:
        await turns.open(db, call_id)
        request = await turns.prepare_reply(db, call_id, user_item_id=None, user_text=None)
        assert request.messages[-1].content == CALL_OPENING_CUE
        assert (await db.execute(select(Message))).scalars().all() == []


async def test_reply_is_saved_with_interruption_and_latency(
    voice_app: FastAPI, vclient: httpx.AsyncClient
) -> None:
    headers = await login(vclient)
    call_id = uuid.UUID((await _start(vclient, headers))["call_id"])
    turns = _turns(voice_app)
    async with voice_app.state.session_factory() as db:
        await turns.open(db, call_id)
        await turns.prepare_reply(db, call_id, user_item_id="u1", user_text="Selam")
        timings = TurnTimings(e2e_ms=640.0, llm_ttft_ms=300.0, tts_ttfb_ms=120.0)
        for _ in range(2):
            await turns.save_reply(
                db, call_id, item_id="a1", text="Selam! Nasıl", interrupted=True, timings=timings
            )
        messages = (await db.execute(select(Message).order_by(Message.created_at))).scalars().all()
        assert [(m.role, m.content, m.interrupted) for m in messages] == [
            ("user", "Selam", False),
            ("assistant", "Selam! Nasıl", True),
        ]
        latencies = (await db.execute(select(TurnLatency))).scalars().all()
        assert len(latencies) == 1 and latencies[0].e2e_ms == 640.0

    report = (await vclient.get("/voice/latency", headers=headers)).json()
    assert report["stages"]["e2e_ms"] == {"p50": 640.0, "p95": 640.0, "count": 1}
    assert report["targets_ms"]["e2e_ms"]["p50"] == 800.0
    assert len(report["turns"]) == 1

    other = await login(vclient, "someone")
    assert (await vclient.get("/voice/latency", headers=other)).json()["turns"] == []


async def test_history_from_text_chat_reaches_the_voice_prompt(
    voice_app: FastAPI, vclient: httpx.AsyncClient
) -> None:
    headers = await login(vclient)
    r = await vclient.post("/chat/conversations", headers=headers, json={})
    conversation = r.json()["id"]
    await vclient.post(
        f"/chat/conversations/{conversation}/messages",
        headers=headers,
        json={"content": "Kedimin adı Pamuk", "idempotency_key": "text-key-1"},
    )
    call_id = uuid.UUID((await _start(vclient, headers))["call_id"])
    async with voice_app.state.session_factory() as db:
        request = await _turns(voice_app).prepare_reply(
            db, call_id, user_item_id="u1", user_text="Neden bahsediyorduk?"
        )
    assert request.messages[0].content == "Kedimin adı Pamuk"


async def test_ended_call_cannot_be_opened_by_the_agent(
    voice_app: FastAPI, vclient: httpx.AsyncClient
) -> None:
    headers = await login(vclient)
    call = await _start(vclient, headers)
    await vclient.post(f"/voice/calls/{call['call_id']}/end", headers=headers)
    async with voice_app.state.session_factory() as db:
        with pytest.raises(CallNotFoundError):
            await _turns(voice_app).open(db, uuid.UUID(call["call_id"]))
        assert await _turns(voice_app).is_ended(db, uuid.UUID(call["call_id"]))
