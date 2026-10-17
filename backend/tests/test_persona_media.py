"""Ses ve yüz kataloğu (config/media.yaml): ayrıştırma, sağlayıcı seçenekleri, yerel görseller."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.persona.media import MediaNotConfiguredError, load_catalog, media_image


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 12)).save(out, format="PNG")
    return out.getvalue()


CATALOG = """
personas:
  eva: { voice: eva, avatar: eva }
voices:
  eva: { name: EVA, mock: eva-mock, elevenlabs: "el-eva" }
  deniz: { name: Deniz, mock: deniz-mock, elevenlabs: "" }
avatars:
  eva: { name: EVA, mock: eva-mock, lemonslice: "file:media/eva.png" }
  ada: { name: Ada, lemonslice: "agent-ada" }
"""


@pytest.fixture
def config(tmp_path: Path) -> Path:
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "eva.png").write_bytes(_png())
    (tmp_path / "media" / "notes.txt").write_text("not an image", encoding="utf-8")
    (tmp_path.parent / "outside.png").write_bytes(_png())
    path = tmp_path / "media.yaml"
    path.write_text(CATALOG, encoding="utf-8")
    return path


def test_catalog_lists_only_options_set_for_the_provider(config: Path) -> None:
    catalog = load_catalog(config)
    assert [o.key for o in catalog.available("voice", "mock")] == ["eva", "deniz"]
    assert [o.key for o in catalog.available("voice", "elevenlabs")] == ["eva"], "empty ids skip"
    assert [o.key for o in catalog.available("avatar", "lemonslice")] == ["eva", "ada"]
    assert catalog.default("eva", "voice") == "eva"
    assert catalog.provider_id("avatar", "ada", "lemonslice") == "agent-ada"
    with pytest.raises(MediaNotConfiguredError):
        catalog.provider_id("voice", "deniz", "elevenlabs")


@pytest.mark.parametrize(
    "bad",
    [
        "voices:\n  own: { name: X }\n",  # "own" ayrılmış
        "voices:\n  Büyük: { name: X }\n",  # anahtar biçimi
        "voices:\n  a: { mock: x }\n",  # adı yok
        "voices:\n  a: { name: A }\navatars: {}\npersonas:\n  eva: { voice: a, avatar: yok }\n",
    ],
)
def test_bad_catalog_is_rejected(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        load_catalog(path)


def test_repo_catalogs_parse() -> None:
    settings = Settings(_env_file=None)
    catalog = load_catalog(settings.media_config)
    assert catalog.default("eva", "voice") == "eva"
    assert len(catalog.available("voice", "elevenlabs")) >= 5


def test_reads_a_local_image_next_to_the_config(config: Path) -> None:
    image = media_image(config, load_catalog(config).provider_id("avatar", "eva", "lemonslice"))
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
