"""Karakter engel listeleri (CLAUDE.md §9.1): telifli karakterler ve hassas figürler.

Kullanıcının oluşturduğu karakterin **adı** listedeki bir terimi içeriyorsa karakter oluşturulamaz.
Eşleşme Türkçe karakter ve büyük/küçük harf duyarsızdır ("Örümcek Adam" = "orumcek adam"),
noktalama boşluk sayılır ("Hz." = "hz", "Spider-Man" = "spider man") ve tam kelime/kelime grubu
aranır ("batman" eşleşir, "batmanli" eşleşmez). Liste dosyaları config/ altında; değişince
uygulama yeniden başlatılmadan da okunur (dosya değişiklik zamanına göre önbellek).
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

BlockCategory = Literal["copyright", "sacred", "hate", "legal"]

_TURKISH = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
    }
)
_NON_WORD = re.compile(r"[^a-z0-9]+")


class BlocklistConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BlockMatch:
    category: BlockCategory
    term: str


def normalize(text: str) -> str:
    """Karşılaştırma biçimi: Türkçe harfler sadeleşir, aksanlar düşer, küçük harf, kelimeler
    arasında tek boşluk."""
    text = text.translate(_TURKISH)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return _NON_WORD.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Blocklist:
    terms: tuple[tuple[BlockCategory, str], ...]  # (kategori, normalize edilmiş terim)

    def check(self, name: str) -> BlockMatch | None:
        padded = f" {normalize(name)} "
        for category, term in self.terms:
            if f" {term} " in padded:
                return BlockMatch(category=category, term=term)
        return None


def _terms(raw: object, where: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(t, str) and t.strip() for t in raw):
        raise BlocklistConfigError(f"{where}: must be a list of non-empty strings")
    return [normalize(t) for t in raw]


def load_blocklist(franchises: Path, sensitive: Path) -> Blocklist:
    try:
        fr = yaml.safe_load(franchises.read_text(encoding="utf-8")) or {}
        se = yaml.safe_load(sensitive.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise BlocklistConfigError(str(exc)) from exc
    if not isinstance(fr, dict) or not isinstance(se, dict):
        raise BlocklistConfigError("blocklist files must be mappings")
    unknown = set(se) - {"sacred", "hate", "legal"}
    if unknown:
        raise BlocklistConfigError(f"{sensitive}: unknown categories {sorted(unknown)}")
    terms: list[tuple[BlockCategory, str]] = [
        ("copyright", t) for t in _terms(fr.get("terms"), f"{franchises}:terms")
    ]
    for category in ("sacred", "hate", "legal"):
        terms += [(category, t) for t in _terms(se.get(category), f"{sensitive}:{category}")]
    return Blocklist(terms=tuple(terms))


_CACHE: dict[tuple[Path, Path], tuple[tuple[float, float], Blocklist]] = {}


def blocklist_for(franchises: Path, sensitive: Path) -> Blocklist:
    """Dosyalar değişmediyse aynı listeyi döner; değiştiyse yeniden okur."""
    key = (franchises, sensitive)
    stamp = (franchises.stat().st_mtime, sensitive.stat().st_mtime)
    cached = _CACHE.get(key)
    if cached is None or cached[0] != stamp:
        cached = (stamp, load_blocklist(franchises, sensitive))
        _CACHE[key] = cached
    return cached[1]
