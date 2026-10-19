"""Ses ve yüz kataloğu (``config/media.yaml``).

Katalogda hazır sesler (``voices``) ve hazır yüzler (``avatars``) durur; her birinin her
sağlayıcıdaki id'si ayrı yazılır. Personaların varsayılanı ``personas`` altında (EVA'nın sesi
EVA'ya özgüdür). Kullanıcı EVA'yı istediği sesle ve istediği yüzle kullanabilir; ayrıca kendi
rızalı klon sesini (``own``) ve kendi fotoğrafını (``own``) seçebilir.

Fotoğraftan çalışan avatar sağlayıcıları (ör. LemonSlice) için yüz değeri ``file:<yol>`` olabilir:
yol, media.yaml'ın bulunduğu klasöre göredir ve görsel her görüşmede oradan yüklenir.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from app.providers.base import EnrollmentSample

MediaKind = Literal["voice", "avatar"]
# Katalog anahtarı yerine "kullanıcının kendi rızalı klonu / fotoğrafı".
OWN = "own"
# Katalog anahtarı yerine "karakterin kendi yüz görseli" (Karakter Stüdyosu, ADR 0009).
PERSONA_FACE = "persona"
FILE_PREFIX = "file:"
KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class MediaNotConfiguredError(LookupError):
    """Seçili sağlayıcı için bu ses/yüz henüz ayarlanmamış."""


@dataclass(frozen=True, slots=True)
class MediaOption:
    key: str
    name: str
    # sağlayıcı adı -> o sağlayıcıdaki id (boş olanlar alınmaz)
    ids: dict[str, str]


@dataclass(frozen=True, slots=True)
class MediaCatalog:
    path: Path
    voices: dict[str, MediaOption]
    avatars: dict[str, MediaOption]
    # persona kısa adı -> {"voice": anahtar, "avatar": anahtar}
    defaults: dict[str, dict[str, str]]

    def options(self, kind: MediaKind) -> dict[str, MediaOption]:
        return self.voices if kind == "voice" else self.avatars

    def available(self, kind: MediaKind, provider: str) -> list[MediaOption]:
        """Bu sağlayıcıda id'si olan seçenekler (katalogdaki sırayla)."""
        return [o for o in self.options(kind).values() if provider in o.ids]

    def default(self, persona_slug: str, kind: MediaKind) -> str:
        key = self.defaults.get(persona_slug, {}).get(kind)
        if not key:
            raise MediaNotConfiguredError(f"{persona_slug}.{kind} has no default")
        return key

    def provider_id(self, kind: MediaKind, key: str, provider: str) -> str:
        option = self.options(kind).get(key)
        if option is None or provider not in option.ids:
            raise MediaNotConfiguredError(f"{kind} {key!r} is not set for {provider}")
        return option.ids[provider]


def _options(raw: Any, section: str) -> dict[str, MediaOption]:
    if not isinstance(raw, dict):
        raise ValueError(f"media.yaml: {section} must be a mapping")
    out: dict[str, MediaOption] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not KEY_PATTERN.match(key) or key in (OWN, PERSONA_FACE):
            raise ValueError(f"media.yaml: bad {section} key {key!r}")
        if not isinstance(value, dict) or not isinstance(value.get("name"), str):
            raise ValueError(f"media.yaml: {section}.{key} needs a name")
        ids = {str(p): v for p, v in value.items() if p != "name" and isinstance(v, str) and v}
        out[key] = MediaOption(key=key, name=value["name"], ids=ids)
    return out


@lru_cache
def load_catalog(path: Path) -> MediaCatalog:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: must be a mapping")
    voices = _options(data.get("voices", {}), "voices")
    avatars = _options(data.get("avatars", {}), "avatars")
    defaults: dict[str, dict[str, str]] = {}
    for slug, choice in (data.get("personas") or {}).items():
        if not isinstance(choice, dict):
            raise ValueError(f"media.yaml: personas.{slug} must be a mapping")
        voice, avatar = choice.get("voice"), choice.get("avatar")
        if voice not in voices or avatar not in avatars:
            raise ValueError(f"media.yaml: personas.{slug} points to unknown voice/avatar")
        defaults[str(slug)] = {"voice": voice, "avatar": avatar}
    return MediaCatalog(path=path, voices=voices, avatars=avatars, defaults=defaults)


def media_image(path: Path, value: str) -> EnrollmentSample:
    """``file:`` ile verilmiş katalog görselini okur. Yol media.yaml'ın klasörünün dışına
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
