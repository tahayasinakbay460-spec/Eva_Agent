"""Miras güvenlik anahtarı (CLAUDE.md §8.3, ADR 0010).

Anahtar 20 rastgele bayttır (160 bit, işletim sisteminin CSPRNG'si). İnsanın okuyup yazabilmesi
için Crockford Base32 ile yazılır (karıştırılan I, L, O, U harfleri yok), 4'lü gruplara bölünür ve
sonuna Crockford'un mod 37 kontrol karakteri eklenir: ``EVA-XXXX-...-XXXX-C``. Kontrol karakteri
yazım hatalarını veritabanına hiç gitmeden yakalar.

Veritabanında anahtarın kendisi değil, gizli bir "biber" (pepper) ile alınmış HMAC-SHA-256 özeti
durur. Biber veritabanında değildir; veritabanı tek başına sızsa bile özetlerden anahtar tahmin
edilemez.
"""

import base64
import hashlib
import hmac
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

KEY_BYTES = 20  # 160 bit (§8.3: en az 128)
PEPPER_BYTES = 32
PREFIX = "EVA"
GROUP = 4

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Crockford: kontrol karakteri için alfabeye beş sembol daha eklenir (mod 37).
_CHECK_ALPHABET = _ALPHABET + "*~$=U"
_DECODE = {c: i for i, c in enumerate(_ALPHABET)}
# Okurken karışan harfler: O -> 0, I/L -> 1.
_ALIASES = str.maketrans({"O": "0", "I": "1", "L": "1"})
_BODY_LEN = KEY_BYTES * 8 // 5  # 32 karakter


class InvalidKeyFormatError(ValueError):
    """Anahtar biçimi bozuk (uzunluk, karakter ya da kontrol karakteri)."""


def _encode(value: int) -> str:
    chars = []
    for _ in range(_BODY_LEN):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def _check_char(value: int) -> str:
    return _CHECK_ALPHABET[value % 37]


def generate_key() -> str:
    """Yeni bir anahtar: ``EVA-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-C``."""
    value = int.from_bytes(secrets.token_bytes(KEY_BYTES), "big")
    body = _encode(value)
    groups = [body[i : i + GROUP] for i in range(0, len(body), GROUP)]
    return "-".join([PREFIX, *groups, _check_char(value)])


def normalize(raw: str) -> str:
    """Kullanıcının yazdığını tek biçime getirir: büyük harf, boşluk/tire yok, ön ek yok,
    karışan harfler düzeltilmiş. Biçim bozuksa ``InvalidKeyFormatError``."""
    text = "".join(raw.split()).replace("-", "").upper()
    if text.startswith(PREFIX):
        text = text[len(PREFIX) :]
    if len(text) != _BODY_LEN + 1:
        raise InvalidKeyFormatError("length")
    body, check = text[:-1].translate(_ALIASES), text[-1]
    if check in "OIL":
        check = check.translate(_ALIASES)
    value = 0
    for c in body:
        digit = _DECODE.get(c)
        if digit is None:
            raise InvalidKeyFormatError("character")
        value = (value << 5) | digit
    if not hmac.compare_digest(_check_char(value), check):
        raise InvalidKeyFormatError("check")
    return body + check


def digest(pepper: bytes, raw: str) -> str:
    """Saklanan özet: ``HMAC-SHA-256(pepper, normalize(raw))`` (hex)."""
    return hmac.new(pepper, normalize(raw).encode("ascii"), hashlib.sha256).hexdigest()


def load_or_create_dev_pepper(path: Path) -> bytes:
    """Geliştirme için biberi yerel bir dosyadan okur, yoksa oluşturur (git'e girmez).
    Silinirse eski dev anahtarları geçersiz olur; geliştirmede kabul edilebilir."""
    if path.exists():
        return base64.b64decode(path.read_text(encoding="ascii").strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    pepper = secrets.token_bytes(PEPPER_BYTES)
    path.write_text(base64.b64encode(pepper).decode("ascii"), encoding="ascii")
    return pepper


class LegacyConfigError(RuntimeError):
    pass


def load_pepper(*, configured: str | None, dev_file: Path, is_dev: bool) -> bytes:
    """Biberi ayardan (base64) okur; dev/test'te ayar yoksa yerel dosyadan. Gerçek ortamda ayar
    yoksa uygulama hiç açılmaz (anahtarlar zayıf bir biberle korunmasın)."""
    if configured:
        try:
            pepper = base64.b64decode(configured, validate=True)
        except ValueError as exc:
            raise LegacyConfigError("EVA_LEGACY_KEY_PEPPER must be base64") from exc
        if len(pepper) < PEPPER_BYTES:
            raise LegacyConfigError("EVA_LEGACY_KEY_PEPPER must be at least 32 bytes")
        return pepper
    if not is_dev:
        raise LegacyConfigError("EVA_LEGACY_KEY_PEPPER is required outside dev/test")
    return load_or_create_dev_pepper(dev_file)


def pepper_from_settings(settings: "Settings") -> bytes:
    """API ve işçi biberi aynı yerden okusun."""
    return load_pepper(
        configured=(
            settings.legacy_key_pepper.get_secret_value() if settings.legacy_key_pepper else None
        ),
        dev_file=settings.dev_legacy_pepper_file,
        is_dev=settings.is_dev,
    )
