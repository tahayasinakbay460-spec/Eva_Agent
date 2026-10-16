import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.providers.base import LLMEvent, LLMRequest, ProviderError, StreamEnd, TextDelta
from tests.conftest import login, parse_sse


async def _new_conversation(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    r = await client.post("/chat/conversations", json={}, headers=headers)
    assert r.status_code == 201, r.text
    conversation_id: str = r.json()["id"]
    return conversation_id


async def _send(
    client: httpx.AsyncClient, headers: dict[str, str], conversation_id: str, text: str, key: str
) -> httpx.Response:
    return await client.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"content": text, "idempotency_key": key},
        headers=headers,
    )


async def test_create_conversation_uses_default_eva(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/chat/conversations", json={}, headers=auth_headers)
    assert r.status_code == 201
    personas = (await client.get("/personas", headers=auth_headers)).json()
    eva = next(p for p in personas if p["slug"] == "eva")
    assert r.json()["persona_id"] == eva["id"]


async def test_stream_reply_and_persist(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    conversation_id = await _new_conversation(client, auth_headers)
    r = await _send(client, auth_headers, conversation_id, "selam eva", "key-0000001")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(r.text)
    names = [name for name, _ in events]
    assert names[0] == "message_start"
    assert names[-1] == "done"
    assert "delta" in names
    reply = "".join(d["text"] for name, d in events if name == "delta")
    assert "selam eva" in reply
    assert events[-1][1]["stop_reason"] == "end_turn"
    assert events[-1][1]["interrupted"] is False

    msgs = (
        await client.get(f"/chat/conversations/{conversation_id}/messages", headers=auth_headers)
    ).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == reply
    assert msgs[1]["id"] == events[-1][1]["assistant_message_id"]


async def test_idempotent_resend_replays_without_new_messages(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    conversation_id = await _new_conversation(client, auth_headers)
    first = parse_sse(
        (await _send(client, auth_headers, conversation_id, "bir", "same-key-1")).text
    )
    second = parse_sse(
        (await _send(client, auth_headers, conversation_id, "bir", "same-key-1")).text
    )
    assert first[-1][1]["assistant_message_id"] == second[-1][1]["assistant_message_id"]
    msgs = (
        await client.get(f"/chat/conversations/{conversation_id}/messages", headers=auth_headers)
    ).json()
    assert len(msgs) == 2


async def test_other_users_conversation_is_invisible(client: httpx.AsyncClient) -> None:
    alice = await login(client, "alice")
    bob = await login(client, "bob")
    conversation_id = await _new_conversation(client, alice)

    assert (
        await client.get(f"/chat/conversations/{conversation_id}", headers=bob)
    ).status_code == 404
    assert (
        await client.get(f"/chat/conversations/{conversation_id}/messages", headers=bob)
    ).status_code == 404
    r = await _send(client, bob, conversation_id, "merhaba", "bob-key-0001")
    assert r.status_code == 404
    assert [c["id"] for c in (await client.get("/chat/conversations", headers=bob)).json()] == []


async def test_unknown_conversation_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.get(f"/chat/conversations/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


async def test_message_validation(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    conversation_id = await _new_conversation(client, auth_headers)
    r = await _send(client, auth_headers, conversation_id, "", "key-0000001")
    assert r.status_code == 422
    r = await _send(client, auth_headers, conversation_id, "x", "short")
    assert r.status_code == 422


class _FailingProvider:
    name = "failing"

    def __init__(self, after: int) -> None:
        self._after = after

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        for i in range(self._after):
            yield TextDelta(f"p{i} ")
        raise ProviderError("boom", retryable=True)


async def test_provider_error_mid_stream_saves_partial_and_reports(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    app.state.registry.register_llm("mock", _FailingProvider(after=2))
    conversation_id = await _new_conversation(client, auth_headers)
    events = parse_sse(
        (await _send(client, auth_headers, conversation_id, "hey", "err-key-001")).text
    )
    assert events[-1][0] == "error"
    assert events[-1][1] == {"code": "provider_error", "retryable": True}
    msgs = (
        await client.get(f"/chat/conversations/{conversation_id}/messages", headers=auth_headers)
    ).json()
    assert msgs[-1]["role"] == "assistant"
    assert msgs[-1]["interrupted"] is True
    assert msgs[-1]["content"] == "p0 p1 "


class _RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        self.requests.append(request)
        yield TextDelta("ok")
        yield StreamEnd(stop_reason="end_turn")


async def test_history_is_sent_in_alternating_order(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = _RecordingProvider()
    app.state.registry.register_llm("mock", provider)
    conversation_id = await _new_conversation(client, auth_headers)
    await _send(client, auth_headers, conversation_id, "bir", "k-00000001")
    await _send(client, auth_headers, conversation_id, "iki", "k-00000002")

    req = provider.requests[-1]
    assert [m.role for m in req.messages] == ["user", "assistant", "user"]
    assert req.messages[-1].content == "iki"
    assert req.system[0].cacheable is True
    assert "Core rules" in req.system[0].text
    assert "EVA" in req.system[1].text


async def test_history_order_survives_a_frozen_clock(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coarse clocks (Windows) can give a reply the same timestamp as its prompt."""
    frozen = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    monkeypatch.setattr("app.services.chat_service.utcnow", lambda: frozen)
    provider = _RecordingProvider()
    app.state.registry.register_llm("mock", provider)
    conversation_id = await _new_conversation(client, auth_headers)
    for i, text in enumerate(["bir", "iki", "üç"]):
        await _send(client, auth_headers, conversation_id, text, f"frozen-{i:04d}")

    req = provider.requests[-1]
    assert [(m.role, m.content) for m in req.messages] == [
        ("user", "bir"),
        ("assistant", "ok"),
        ("user", "iki"),
        ("assistant", "ok"),
        ("user", "üç"),
    ]
    msgs = (
        await client.get(f"/chat/conversations/{conversation_id}/messages", headers=auth_headers)
    ).json()
    assert [m["content"] for m in msgs] == ["bir", "ok", "iki", "ok", "üç", "ok"]
