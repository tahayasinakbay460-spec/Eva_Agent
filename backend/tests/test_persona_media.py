"""Persona ses/yüz ayarı (config/media.yaml): ``file:`` ile verilen yerel görseller."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.persona.media import MediaNotConfiguredError, media_id, media_image


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 12)).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def config(tmp_path: Path) -> Path:
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "eva.png").write_bytes(_png())
    (tmp_path / "media" / "notes.txt").write_text("not an image", encoding="utf-8")
    (tmp_path.parent / "outside.png").write_bytes(_png())
    path = tmp_path / "media.yaml"
    path.write_text(
        "eva:\n  voice:\n    mock: eva-mock\n"
        "  avatar:\n    lemonslice: 'file:media/eva.png'\n    mock: eva-mock\n",
        encoding="utf-8",
    )
    return path


def test_reads_a_local_image_next_to_the_config(config: Path) -> None:
    value = media_id(config, "eva", "avatar", "lemonslice")
    image = media_image(config, value)
    assert image.media_type == "image/png" and image.data == _png()


@pytest.mark.parametrize(
    "value",
    [
        "eva-mock",  # dosya değil, sağlayıcı id'si
        "file:media/missing.png",
        "file:media/notes.txt",  # görsel değil
        "file:../outside.png",  # config klasörünün dışı
        "file:media",  # klasör
    ],
)
def test_refuses_anything_else(config: Path, value: str) -> None:
    with pytest.raises(MediaNotConfiguredError):
        media_image(config, value)


async def test_persona_call_sends_the_local_image_only_to_image_avatars(
    tmp_path: Path, config: Path
) -> None:
    import uuid

    import httpx

    from app.services.voice_service import CallMedia, CallTurns, MediaNotReadyError
    from tests.conftest import build_app, login, make_settings
    from tests.test_voice import LK

    app = await build_app(make_settings(tmp_path, media_config=config, **LK))
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await login(client, "ayse")
            r = await client.post("/voice/calls", headers=headers, json={"mode": "video"})
            assert r.status_code == 201, r.text
            call_id = uuid.UUID(r.json()["call_id"])

        async def media(accepts_image: bool) -> CallMedia:
            async with app.state.session_factory() as db:
                return await CallTurns(app.state.chat_service).call_media(
                    db,
                    call_id,
                    media_config=config,
                    tts_provider="mock",
                    avatar_provider="lemonslice",
                    avatar_accepts_image=accepts_image,
                    store=app.state.store,
                )

        result = await media(True)
        assert result.avatar_image is not None and result.avatar_image.data == _png()
        with pytest.raises(MediaNotReadyError):
            await media(False)
    finally:
        await app.state.engine.dispose()
