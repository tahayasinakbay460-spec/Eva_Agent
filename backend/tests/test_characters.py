"""Karakter Stüdyosu: /characters uçları, görünürlük, yüz görseli ve görüşmede karakter yüzü."""

import io
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select

from app.models.biometric import AuditLog
from app.models.call import CallSession
from app.persona.media import PERSONA_FACE
from app.services.voice_service import CallMedia, CallTurns, MediaNotReadyError
from tests.conftest import build_app, login, make_settings
from tests.test_voice import LK

CATALOG = """
personas:
  eva: { voice: eva, avatar: eva }
voices:
  eva: { name: EVA, mock: eva-mock }
  deep: { name: Deep, mock: deep-mock }
avatars:
  eva: { name: EVA, mock: eva-mock }
"""

CHARACTER = {
    "name": "Deniz",
    "identity": "İzmirli müzisyen.",
    "personality": "Sıcak, şakacı.",
    "speaking_style": "Kısa mesajlar.",
    "example_dialogs": [{"user": "selam", "persona": "selaam, naber?"}],
}


def _jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (16, 24), "red")
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


@pytest.fixture
async def app(tmp_path: Path) -> Any:
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


def _photo_avatar(app: FastAPI) -> None:
    """Mock avatarı fotoğraftan çalışan bir sağlayıcı gibi davrandır (LemonSlice benzeri)."""
    app.state.registry.avatar("realtime").accepts_image = True


async def _create(client: httpx.AsyncClient, headers: dict[str, str], **extra: Any) -> str:
    r = await client.post("/characters", headers=headers, json={**CHARACTER, **extra})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _upload_face(
    client: httpx.AsyncClient, headers: dict[str, str], cid: str, *, confirmed: bool = True
) -> httpx.Response:
    return await client.put(
        f"/characters/{cid}/face",
        params={"rights_confirmed": str(confirmed).lower()},
        headers={**headers, "Content-Type": "image/jpeg"},
        content=_jpeg_with_exif(),
    )


async def test_character_endpoints_require_login(client: httpx.AsyncClient) -> None:
    cid = uuid.uuid4()
    assert (await client.get("/characters")).status_code == 401
    assert (await client.post("/characters", json=CHARACTER)).status_code == 401
    assert (await client.get(f"/characters/{cid}")).status_code == 401
    assert (await client.put(f"/characters/{cid}", json=CHARACTER)).status_code == 401
    assert (await client.delete(f"/characters/{cid}")).status_code == 401
    assert (await client.put(f"/characters/{cid}/face", content=b"x")).status_code == 401
    assert (await client.get(f"/characters/{cid}/face")).status_code == 401


async def test_create_list_and_public_visibility(client: httpx.AsyncClient) -> None:
    ayse, mehmet = await login(client, "ayse"), await login(client, "mehmet")
    public_id = await _create(client, ayse)
    private_id = await _create(client, ayse, name="Gizli", visibility="private")

    mine = (await client.get("/characters?scope=mine", headers=ayse)).json()
    assert {c["id"] for c in mine} == {public_id, private_id}
    assert all(c["is_mine"] for c in mine)

    public = [
        c for c in (await client.get("/characters", headers=mehmet)).json() if not c["builtin"]
    ]
    assert [c["id"] for c in public] == [public_id]
    assert public[0]["is_mine"] is False and public[0]["has_face"] is False

    # Başkasının gizli karakteri "yok" sayılır (IDOR).
    assert (await client.get(f"/characters/{private_id}", headers=mehmet)).status_code == 404
    assert (await client.get(f"/characters/{public_id}", headers=mehmet)).status_code == 200
    personas = (await client.get("/personas", headers=mehmet)).json()
    assert public_id in {p["id"] for p in personas}
    assert private_id not in {p["id"] for p in personas}


async def test_only_owner_can_edit_delete_or_set_face(client: httpx.AsyncClient) -> None:
    ayse, mehmet = await login(client, "ayse"), await login(client, "mehmet")
    cid = await _create(client, ayse)
    changed = {**CHARACTER, "name": "Hacked"}
    assert (await client.put(f"/characters/{cid}", headers=mehmet, json=changed)).status_code == 404
    assert (await client.delete(f"/characters/{cid}", headers=mehmet)).status_code == 404
    assert (await _upload_face(client, mehmet, cid)).status_code == 404
    assert (await client.delete(f"/characters/{cid}/face", headers=mehmet)).status_code == 404

    r = await client.put(f"/characters/{cid}", headers=ayse, json={**CHARACTER, "name": "Ece"})
    assert r.status_code == 200 and r.json()["name"] == "Ece"
    assert (await client.delete(f"/characters/{cid}", headers=ayse)).status_code == 204
    assert (await client.get(f"/characters/{cid}", headers=ayse)).status_code == 404


async def test_input_validation(client: httpx.AsyncClient) -> None:
    ayse = await login(client, "ayse")
    assert (await client.post("/characters", headers=ayse, json={"name": ""})).status_code == 422
    too_many = {**CHARACTER, "example_dialogs": [{"user": "a", "persona": "b"}] * 11}
    assert (await client.post("/characters", headers=ayse, json=too_many)).status_code == 422
    r = await client.post("/characters", headers=ayse, json={**CHARACTER, "voice_key": "nope"})
    assert r.status_code == 422 and r.json()["detail"] == "unknown_voice"
    r = await client.post("/characters", headers=ayse, json={**CHARACTER, "voice_key": "deep"})
    assert r.status_code == 201 and r.json()["voice_key"] == "deep"


async def test_face_upload_needs_rights_and_strips_metadata(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    ayse, mehmet = await login(client, "ayse"), await login(client, "mehmet")
    cid = await _create(client, ayse)

    r = await _upload_face(client, ayse, cid, confirmed=False)
    assert r.status_code == 422 and r.json()["detail"] == "rights_not_confirmed"
    r = await client.put(
        f"/characters/{cid}/face",
        params={"rights_confirmed": "true"},
        headers={**ayse, "Content-Type": "image/png"},
        content=_jpeg_with_exif(),
    )
    assert r.status_code == 415, "claimed png, bytes are jpeg"

    r = await _upload_face(client, ayse, cid)
    assert r.status_code == 200 and r.json()["has_face"] is True

    # Herkese açık karakterin yüzünü başkası da görür; temizlenmiş PNG olarak.
    face = await client.get(f"/characters/{cid}/face", headers=mehmet)
    assert face.status_code == 200 and face.headers["content-type"] == "image/png"
    assert b"SecretCam" not in face.content
    with Image.open(io.BytesIO(face.content)) as image:
        assert image.size == (16, 24)

    async with app.state.session_factory() as db:
        actions = (await db.scalars(select(AuditLog.action))).all()
    assert "character.face_set" in actions

    r = await client.delete(f"/characters/{cid}/face", headers=ayse)
    assert r.status_code == 200 and r.json()["has_face"] is False
    assert (await client.get(f"/characters/{cid}/face", headers=mehmet)).status_code == 404


async def test_private_character_face_hidden_from_others(client: httpx.AsyncClient) -> None:
    ayse, mehmet = await login(client, "ayse"), await login(client, "mehmet")
    cid = await _create(client, ayse, visibility="private")
    assert (await _upload_face(client, ayse, cid)).status_code == 200
    assert (await client.get(f"/characters/{cid}/face", headers=mehmet)).status_code == 404
    assert (await client.get(f"/characters/{cid}/face", headers=ayse)).status_code == 200


async def _media(app: FastAPI, call_id: str, *, accepts_image: bool) -> CallMedia:
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


async def test_video_call_with_someone_elses_public_character_uses_its_face_and_voice(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    _photo_avatar(app)
    ayse, mehmet = await login(client, "ayse"), await login(client, "mehmet")
    cid = await _create(client, ayse, voice_key="deep")
    assert (await _upload_face(client, ayse, cid)).status_code == 200

    options = (await client.get(f"/media/options?persona_id={cid}", headers=mehmet)).json()
    assert options["persona_avatar"] is True
    assert options["defaults"] == {"voice": "deep", "avatar": PERSONA_FACE}

    r = await client.post("/voice/calls", headers=mehmet, json={"mode": "video", "persona_id": cid})
    assert r.status_code == 201, r.text
    call_id = r.json()["call_id"]
    async with app.state.session_factory() as db:
        call = await db.get(CallSession, uuid.UUID(call_id))
        assert call is not None and call.avatar_key == PERSONA_FACE

    media = await _media(app, call_id, accepts_image=True)
    assert media.voice_id == "deep-mock"
    assert media.avatar_image is not None and media.avatar_image.media_type == "image/png"
    with pytest.raises(MediaNotReadyError):
        await _media(app, call_id, accepts_image=False)


async def test_persona_face_choice_needs_a_face(app: FastAPI, client: httpx.AsyncClient) -> None:
    _photo_avatar(app)
    ayse = await login(client, "ayse")
    cid = await _create(client, ayse)
    r = await client.put(
        "/media/preferences", headers=ayse, json={"persona_id": cid, "avatar": PERSONA_FACE}
    )
    assert r.status_code == 409 and r.json()["detail"] == "no_persona_face"
    assert (await _upload_face(client, ayse, cid)).status_code == 200
    r = await client.put(
        "/media/preferences", headers=ayse, json={"persona_id": cid, "avatar": PERSONA_FACE}
    )
    assert r.status_code == 200 and r.json()["selected"]["avatar"] == PERSONA_FACE


async def test_chat_with_public_character(client: httpx.AsyncClient) -> None:
    ayse, mehmet = await login(client, "ayse"), await login(client, "mehmet")
    cid = await _create(client, ayse)
    r = await client.post("/chat/conversations", headers=mehmet, json={"persona_id": cid})
    assert r.status_code == 201, r.text
    private_id = await _create(client, ayse, visibility="private")
    r = await client.post("/chat/conversations", headers=mehmet, json={"persona_id": private_id})
    assert r.status_code == 404


# --- engel listeleri (§9.1) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Batman", "blocked_copyright"),
        ("Örümcek Adam", "blocked_copyright"),
        ("SPIDER-MAN", "blocked_copyright"),
        ("Harry Potter ve ben", "blocked_copyright"),
        ("Hz. Muhammed", "blocked_sacred"),
        ("Adolf Hitler", "blocked_hate"),
        ("Mustafa Kemal Atatürk", "blocked_legal"),
    ],
)
async def test_blocked_names_are_rejected(client: httpx.AsyncClient, name: str, code: str) -> None:
    headers = await login(client, "ayse")
    r = await client.post("/characters", headers=headers, json={**CHARACTER, "name": name})
    assert r.status_code == 422 and r.json()["detail"] == code


@pytest.mark.parametrize(
    "name",
    ["Muhammed Yılmaz", "Elsa", "Mario", "Mustafa Kemal Demir", "Batmanlı Deniz", "Thor"],
)
async def test_ordinary_names_are_not_blocked(client: httpx.AsyncClient, name: str) -> None:
    """Gerçek insan adı olabilen ya da kamu malı adlar engellenmez (yanlış pozitif yok)."""
    headers = await login(client, "ayse")
    r = await client.post("/characters", headers=headers, json={**CHARACTER, "name": name})
    assert r.status_code == 201, r.text


async def test_identity_text_is_not_scanned(client: httpx.AsyncClient) -> None:
    headers = await login(client, "ayse")
    body = {**CHARACTER, "identity": "Harry Potter hayranı, Allah'a inanan bir dede."}
    assert (await client.post("/characters", headers=headers, json=body)).status_code == 201


async def test_rename_into_a_blocked_name_is_rejected(client: httpx.AsyncClient) -> None:
    headers = await login(client, "ayse")
    cid = await _create(client, headers)
    r = await client.put(
        f"/characters/{cid}", headers=headers, json={**CHARACTER, "name": "Darth Vader"}
    )
    assert r.status_code == 422 and r.json()["detail"] == "blocked_copyright"


# --- hazır karakterler -------------------------------------------------------------------


async def test_builtin_characters_are_listed_first_and_read_only(
    client: httpx.AsyncClient,
) -> None:
    from app.persona.builtin import BUILTIN_CHARACTERS

    headers = await login(client, "ayse")
    mine = await _create(client, headers)
    public = (await client.get("/characters", headers=headers)).json()
    builtin = [c for c in public if c["builtin"]]
    assert {c["name"] for c in builtin} == {d.name for d in BUILTIN_CHARACTERS.values()}
    assert public[: len(builtin)] == builtin, "built-ins come first"
    assert public[-1]["id"] == mine
    fatih = next(c for c in builtin if c["name"] == "Fatih Sultan Mehmet")
    assert fatih["time_awareness"] == "in_era" and fatih["is_mine"] is False

    # Kimse düzenleyemez, silemez, yüzünü değiştiremez.
    fid = fatih["id"]
    assert (
        await client.put(f"/characters/{fid}", headers=headers, json=CHARACTER)
    ).status_code == 404
    assert (await client.delete(f"/characters/{fid}", headers=headers)).status_code == 404
    assert (await _upload_face(client, headers, fid)).status_code == 404
    # Ama herkes konuşabilir.
    r = await client.post("/chat/conversations", headers=headers, json={"persona_id": fid})
    assert r.status_code == 201


async def test_builtin_definitions_are_system_and_updated_on_startup(app: FastAPI) -> None:
    from app.models.persona import Persona
    from app.persona.builtin import BUILTIN_CHARACTERS
    from app.services import persona_service

    async with app.state.session_factory() as db:
        rows = (await db.scalars(select(Persona).where(Persona.owner_id.is_(None)))).all()
        fatih = next(p for p in rows if p.slug == "fatih-sultan-mehmet")
        assert fatih.definition["source"] == "system"
        fatih.definition = {**fatih.definition, "identity": "eski"}
        await db.commit()
        await persona_service.ensure_builtin_characters(db)
        await db.refresh(fatih)
        assert fatih.definition == BUILTIN_CHARACTERS["fatih-sultan-mehmet"].model_dump()
        # İkinci çalıştırma yeni satır eklemez.
        again = (await db.scalars(select(Persona).where(Persona.owner_id.is_(None)))).all()
        assert len(again) == len(rows)


async def test_builtin_catalog_avatar_comes_from_media_yaml(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    """Sahip media.yaml'a görsel ekleyince kartta ve görüşmede o yüz kullanılır."""
    media = tmp_path / "media"
    media.mkdir(exist_ok=True)
    out = io.BytesIO()
    Image.new("RGB", (8, 12)).save(out, format="PNG")
    (media / "fatih.png").write_bytes(out.getvalue())
    config = tmp_path / "media.yaml"
    config.write_text(
        CATALOG.replace(
            "personas:\n", "personas:\n  fatih-sultan-mehmet: { voice: deep, avatar: fatih }\n"
        )
        + '  fatih: { name: Fatih, mock: "file:media/fatih.png" }\n',
        encoding="utf-8",
    )
    app.state.settings.media_config = config
    _photo_avatar(app)
    headers = await login(client, "ayse")
    fatih = next(
        c
        for c in (await client.get("/characters", headers=headers)).json()
        if c["name"] == "Fatih Sultan Mehmet"
    )
    assert fatih["catalog_avatar"] == "fatih"
    options = (await client.get(f"/media/options?persona_id={fatih['id']}", headers=headers)).json()
    assert options["defaults"] == {"voice": "deep", "avatar": "fatih"}
