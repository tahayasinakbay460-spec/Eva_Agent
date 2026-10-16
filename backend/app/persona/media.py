"""Sistem personalarının ses/yüz id'leri (``config/media.yaml``)."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

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
