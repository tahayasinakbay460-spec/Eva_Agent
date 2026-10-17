"""EVA'nın sesi ve yüzü: /media uçları ve seçimin görüşmeye yansıması."""

import io
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.services.voice_service import CallMedia, CallTurns, MediaNotReadyError
from tests.conftest import build_app, login, make_settings
from tests.test_voice import LK


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 12)).save(out, format="PNG")
    return out.getvalue()


CATALOG = """
personas:
  eva: { voice: eva, avatar: eva }
voices:
  eva: { name: EVA, mock: eva-mock }
  sarah: { name: Sarah, mock: sarah-mock }
  hidden: { name: Hidden, elevenlabs: "x" }
avatars:
  eva: { name: EVA, mock: eva-mock }
  ada: { name: Ada, mock: "file:media/ada.png" }
"""


@pytest.fixture
async def app(tmp_path: Path) -> Any:
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "ada.png").write_bytes(_png())
    config = tmp_path / "media.yaml"
    config.write_text(CATALOG, encoding="utf-8")
    application = await build_app(make_settings(tmp_path, media_config=config, **LK))
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> Any:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _media(app: FastAPI, call_id: str, *, accepts_image: bool = False) -> CallMedia:
    async with app.state.session_factory() as db:
        return await CallTurns(app.state.chat_service).call_media(
            db,
            uuid.UUID(call_id),
            media_config=app.state.settings.media_config,
            tts_provider="mock",
            avatar_provider="mock",
            avatar_accepts_image=accepts_image,
            store=app.state.store,
        )


async def test_media_endpoints_require_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/media/options")).status_code == 401
    assert (await client.put("/media/preferences", json={})).status_code == 401
    assert (await client.post("/media/voices/eva/preview")).status_code == 401
    assert (await client.get("/media/avatars/ada/image")).status_code == 401


async def test_options_list_what_the_configured_providers_can_use(
    client: httpx.AsyncClient,
) -> None:
    headers = await login(client, "ayse")
    body = (await client.get("/media/options", headers=headers)).json()
    assert [v["key"] for v in body["voices"]] == ["eva", "sarah"], "no mock id -> hidden"
    # Sahte avatar fotoğraftan çalışmaz: yerel görselli yüz listelenmez.
    assert [a["key"] for a in body["avatars"]] == ["eva"]
    assert body["selected"] == body["defaults"] == {"voice": "eva", "avatar": "eva"}
    assert body["own_voice"] is False and body["own_avatar"] is False


async def test_choice_is_per_user_and_reaches_the_call(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    ayse = await login(client, "ayse")
    r = await client.put("/media/preferences", headers=ayse, json={"voice": "sarah"})
    assert r.status_code == 200 and r.json()["selected"] == {"voice": "sarah", "avatar": "eva"}

    mehmet = await login(client, "mehmet")
    other = (await client.get("/media/options", headers=mehmet)).json()
    assert other["selected"]["voice"] == "eva", "one user's choice never leaks to another"

    r = await client.post("/voice/calls", headers=ayse, json={"mode": "video"})
    assert (r.json()["voice_key"], r.json()["avatar_key"]) == ("sarah", "eva")
    media = await _media(app, r.json()["call_id"])
    assert (media.voice_id, media.avatar_id) == ("sarah-mock", "eva-mock")

    # Görüşme başlarken seçilen ses görüşme boyunca değişmez.
    await client.put("/media/preferences", headers=ayse, json={})
    assert (await _media(app, r.json()["call_id"])).voice_id == "sarah-mock"
    r = await client.post("/voice/calls", headers=ayse, json={})
    assert r.json()["voice_key"] == "eva" and r.json()["avatar_key"] is None, "reset to default"


@pytest.mark.parametrize(
    ("body", "status", "detail"),
    [
        ({"voice": "hidden"}, 422, "unknown_voice"),  # bu sağlayıcıda yok
        ({"avatar": "ada"}, 422, "unknown_avatar"),  # fotoğraf sağlayıcısı değil
        ({"voice": "own"}, 409, "no_active_voice"),
        ({"avatar": "own"}, 409, "no_active_avatar"),
    ],
)
async def test_invalid_choices_are_refused(
    client: httpx.AsyncClient, body: dict[str, str], status: int, detail: str
) -> None:
    headers = await login(client, "ayse")
    r = await client.put("/media/preferences", headers=headers, json=body)
    assert r.status_code == status and r.json() == {"detail": detail}


async def test_bad_keys_and_unknown_personas(client: httpx.AsyncClient) -> None:
    headers = await login(client, "ayse")
    r = await client.put("/media/preferences", headers=headers, json={"voice": "../x"})
    assert r.status_code == 422
    r = await client.get(
        "/media/options", headers=headers, params={"persona_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404
    r = await client.put(
        "/media/preferences", headers=headers, json={"persona_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404


async def test_voice_preview_only_for_catalog_voices(client: httpx.AsyncClient) -> None:
    headers = await login(client, "ayse")
    r = await client.post("/media/voices/sarah/preview", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF"
    for key in ("hidden", "own", "nope"):
        r = await client.post(f"/media/voices/{key}/preview", headers=headers)
        assert r.status_code == 404, key


async def test_avatar_thumbnail_only_for_local_images(client: httpx.AsyncClient) -> None:
    headers = await login(client, "ayse")
    r = await client.get("/media/avatars/ada/image", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content == _png()
    for key in ("eva", "nope"):
        assert (await client.get(f"/media/avatars/{key}/image", headers=headers)).status_code == 404


async def test_catalog_image_avatar_is_sent_to_photo_providers(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    from app.models.call import CallSession

    headers = await login(client, "ayse")
    r = await client.post("/voice/calls", headers=headers, json={"mode": "video"})
    call_id = r.json()["call_id"]
    async with app.state.session_factory() as db:
        call = await db.get(CallSession, uuid.UUID(call_id))
        assert call is not None
        call.avatar_key = "ada"
        await db.commit()
    media = await _media(app, call_id, accepts_image=True)
    assert media.avatar_image is not None and media.avatar_image.data == _png()
    with pytest.raises(MediaNotReadyError):
        await _media(app, call_id, accepts_image=False)


async def test_browser_may_save_the_choice(client: httpx.AsyncClient) -> None:
    """Web uygulaması seçimi PUT ile kaydeder; CORS ön kontrolü buna izin vermeli."""
    r = await client.options(
        "/media/preferences",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code == 200
    assert "PUT" in r.headers["access-control-allow-methods"]
