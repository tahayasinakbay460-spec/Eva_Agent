"""Anı ekleme, listeleme, düzenleme, silme ve kullanıcılar arası izolasyon testleri."""

import uuid
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.models.memory import Memory
from tests.conftest import login

MEMORY = {
    "content": "Geçen yaz annemle Bodrum'a gittik, çok güldük.",
    "occurred_on": "2025-07-20",
    "people": ["annem"],
    "emotion": "happy",
}


async def _add(client: httpx.AsyncClient, headers: dict[str, str], **override: Any) -> Any:
    r = await client.post("/memories", json={**MEMORY, **override}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --- temel akış -------------------------------------------------------------------


async def test_add_and_list_memory(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await _add(client, auth_headers)
    assert created["source"] == "user_added"
    assert created["kind"] == "episode"
    assert created["people"] == ["annem"]
    assert created["importance"] > 0.5, "kullanıcının eklediği anı daha önemli sayılır"

    listed = (await client.get("/memories", headers=auth_headers)).json()
    assert [m["id"] for m in listed] == [created["id"]]

    personas = (await client.get("/personas", headers=auth_headers)).json()
    eva = next(p for p in personas if p["slug"] == "eva")
    assert created["persona_id"] == eva["id"], "persona verilmezse anı EVA'ya kaydedilir"


async def test_filter_by_kind_and_newest_first(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    first = await _add(client, auth_headers)
    fact = await _add(client, auth_headers, kind="fact", content="Kahveyi sütsüz içer.")
    listed = (await client.get("/memories", headers=auth_headers)).json()
    assert [m["id"] for m in listed] == [fact["id"], first["id"]]
    facts = (await client.get("/memories?kind=fact", headers=auth_headers)).json()
    assert [m["id"] for m in facts] == [fact["id"]]


async def test_edit_memory(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await _add(client, auth_headers)
    r = await client.patch(
        f"/memories/{created['id']}",
        json={"content": "Bodrum'a annem ve teyzemle gittik.", "people": ["annem", "teyzem"]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["people"] == ["annem", "teyzem"]
    assert r.json()["occurred_on"] == "2025-07-20", "gönderilmeyen alan değişmez"

    r = await client.patch(
        f"/memories/{created['id']}",
        json={"occurred_on": None, "emotion": None},
        headers=auth_headers,
    )
    assert r.json()["occurred_on"] is None and r.json()["emotion"] is None


async def test_sensitive_memory_is_excluded_from_legacy(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await _add(
        client, auth_headers, content="Geçen ay ameliyat oldum.", sensitivity="sensitive"
    )
    async with app.state.session_factory() as db:
        row = await db.get(Memory, uuid.UUID(created["id"]))
        assert row is not None and row.legacy_scope == "excluded"
    r = await client.patch(
        f"/memories/{created['id']}", json={"sensitivity": "normal"}, headers=auth_headers
    )
    assert r.status_code == 200
    async with app.state.session_factory() as db:
        row = await db.get(Memory, uuid.UUID(created["id"]))
        assert row is not None and row.legacy_scope == "included"


async def test_forget_really_deletes(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await _add(client, auth_headers)
    r = await client.delete(f"/memories/{created['id']}", headers=auth_headers)
    assert r.status_code == 204
    assert (await client.get("/memories", headers=auth_headers)).json() == []
    async with app.state.session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(Memory))
    assert count == 0, "çöp kutusu yok: satır veritabanından gerçekten silinmeli"
    r = await client.delete(f"/memories/{created['id']}", headers=auth_headers)
    assert r.status_code == 404


# --- girdi doğrulama ---------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"content": ""},
        {"content": "   "},
        {"content": "x" * 2001},
        {"kind": "secret"},
        {"emotion": "bored-to-death"},
        {"people": ["x" * 61]},
        {"people": [f"kişi{i}" for i in range(21)]},
        {"occurred_on": (date.today() + timedelta(days=2)).isoformat()},
        {"sensitivity": "public"},
    ],
)
async def test_invalid_memory_is_rejected(
    client: httpx.AsyncClient, auth_headers: dict[str, str], override: dict[str, Any]
) -> None:
    r = await client.post("/memories", json={**MEMORY, **override}, headers=auth_headers)
    assert r.status_code == 422


# --- yetkisiz erişim (IDOR: başkasının kaydına ID'siyle ulaşmaya çalışmak) ----------


async def test_requires_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/memories")).status_code == 401
    assert (await client.post("/memories", json=MEMORY)).status_code == 401


async def test_users_cannot_see_or_touch_each_others_memories(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    mine = await _add(client, auth_headers)
    other = await login(client, "baska")

    assert (await client.get("/memories", headers=other)).json() == []
    r = await client.patch(f"/memories/{mine['id']}", json={"content": "hack"}, headers=other)
    assert r.status_code == 404
    r = await client.delete(f"/memories/{mine['id']}", headers=other)
    assert r.status_code == 404

    still = (await client.get("/memories", headers=auth_headers)).json()
    assert still[0]["content"] == MEMORY["content"], "başkası değiştirememeli/silememeli"


async def test_unknown_persona_is_rejected(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    fake = "00000000-0000-0000-0000-000000000001"
    r = await client.post("/memories", json={**MEMORY, "persona_id": fake}, headers=auth_headers)
    assert r.status_code == 404
    r = await client.get(f"/memories?persona_id={fake}", headers=auth_headers)
    assert r.status_code == 404


async def test_memory_limit(
    client: httpx.AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.memory_service.MAX_MEMORIES_PER_PERSONA", 2)
    await _add(client, auth_headers)
    await _add(client, auth_headers)
    r = await client.post("/memories", json=MEMORY, headers=auth_headers)
    assert r.status_code == 409


async def test_newest_first_survives_a_frozen_clock(
    client: httpx.AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows saati ~15 ms'de bir ilerler; arka arkaya eklenen anıların sırası karışmamalı."""
    from datetime import UTC, datetime

    frozen = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    monkeypatch.setattr("app.database.utcnow", lambda: frozen)
    ids = [(await _add(client, auth_headers, content=f"Anı {i}"))["id"] for i in range(5)]
    listed = (await client.get("/memories", headers=auth_headers)).json()
    assert [m["id"] for m in listed] == list(reversed(ids))
