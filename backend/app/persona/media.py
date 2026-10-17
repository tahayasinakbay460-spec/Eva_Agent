"""Sistem personalarının ses/yüz id'leri (``config/media.yaml``).

Fotoğraftan çalışan avatar sağlayıcıları (ör. LemonSlice) için değer ``file:<yol>`` olabilir:
yol, media.yaml'ın bulunduğu klasöre göredir ve görsel her görüşmede oradan yüklenir.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from app.providers.base import EnrollmentSample

FILE_PREFIX = "file:"
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
MAX_IMAGE_BYTES = 10 * 1024 * 1024

MediaKind = Literal["voice", "avatar"]


class MediaNotConfiguredError(LookupError):
    """Seçili sağlayıcı için bu personanın sesi/yüzü henüz seçilmemiş."""


@lru_cache
def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: must be a mapping")
    return data


def media_id(path: Path, persona_slug: str, kind: MediaKind, provider: str) -> str:
    value = _load(path).get(persona_slug, {}).get(kind, {}).get(provider)
    if not isinstance(value, str) or not value:
        raise MediaNotConfiguredError(f"{persona_slug}.{kind}.{provider} is not set")
    return value


def media_image(path: Path, value: str) -> EnrollmentSample:
    """``file:`` ile verilmiş persona görselini okur. Yol media.yaml'ın klasörünün dışına
    çıkamaz; yalnızca PNG/JPEG/WebP kabul edilir."""
    if not value.startswith(FILE_PREFIX):
        raise MediaNotConfiguredError(f"{value!r} is not a file reference")
    root = path.parent.resolve()
    target = (root / value.removeprefix(FILE_PREFIX)).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise MediaNotConfiguredError(f"{value!r} does not point to a file under {root}")
    data = target.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        raise MediaNotConfiguredError(f"{value!r} is larger than {MAX_IMAGE_BYTES} bytes")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return EnrollmentSample(data, "image/webp")
    for signature, media_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return EnrollmentSample(data, media_type)
    raise MediaNotConfiguredError(f"{value!r} is not a png/jpeg/webp image")
