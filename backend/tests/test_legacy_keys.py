"""Miras anahtarı: üretim, okuma kolaylığı (normalize), kontrol karakteri, özet ve biber."""

import base64
import re
from pathlib import Path

import pytest

from app.legacy.keys import (
    InvalidKeyFormatError,
    LegacyConfigError,
    digest,
    generate_key,
    load_pepper,
    normalize,
)

PEPPER = b"p" * 32
KEY_RE = re.compile(r"^EVA(-[0-9A-HJKMNP-TV-Z]{4}){8}-[0-9A-HJKMNP-TV-Z*~$=U]$")


def test_generated_keys_have_the_documented_shape_and_are_unique() -> None:
    keys = {generate_key() for _ in range(500)}
    assert len(keys) == 500
    assert all(KEY_RE.match(k) for k in keys)


def test_normalize_accepts_how_people_actually_type_it() -> None:
    key = generate_key()
    canonical = normalize(key)
    sloppy = " " + key.lower().replace("-", " ").replace("0", "o").replace("1", "l") + " "
    assert normalize(sloppy) == canonical
    assert normalize(key.removeprefix("EVA-")) == canonical
    assert digest(PEPPER, sloppy) == digest(PEPPER, key)


@pytest.mark.parametrize("mutate", ["typo", "swap", "short", "garbage"])
def test_typos_are_caught_by_format_check(mutate: str) -> None:
    key = generate_key()
    body = key.split("-")[1:]
    if mutate == "typo":
        first = body[0]
        body[0] = ("Z" if first[0] != "Z" else "Y") + first[1:]
    elif mutate == "swap":
        # Yan yana iki farklı karakterin yeri değişmiş (en sık yazım hatası).
        g, i = next(
            (g, i) for g, grp in enumerate(body[:8]) for i in range(3) if grp[i] != grp[i + 1]
        )
        grp = body[g]
        body[g] = grp[:i] + grp[i + 1] + grp[i] + grp[i + 2 :]
    elif mutate == "short":
        body = body[:-2] + body[-1:]
    else:
        body = ["!!!!"] * 8 + ["X"]
    with pytest.raises(InvalidKeyFormatError):
        normalize("-".join(["EVA", *body]))


def test_digest_depends_on_the_pepper_and_hides_the_key() -> None:
    key = generate_key()
    a, b = digest(PEPPER, key), digest(b"q" * 32, key)
    assert a != b and len(a) == 64
    assert normalize(key) not in a


def test_pepper_is_required_outside_dev(tmp_path: Path) -> None:
    with pytest.raises(LegacyConfigError):
        load_pepper(configured=None, dev_file=tmp_path / "p", is_dev=False)
    with pytest.raises(LegacyConfigError):
        load_pepper(configured=base64.b64encode(b"short").decode(), dev_file=tmp_path, is_dev=False)
    good = base64.b64encode(PEPPER).decode()
    assert load_pepper(configured=good, dev_file=tmp_path / "p", is_dev=False) == PEPPER


def test_dev_pepper_is_created_once_and_reused(tmp_path: Path) -> None:
    path = tmp_path / "pepper"
    first = load_pepper(configured=None, dev_file=path, is_dev=True)
    assert len(first) == 32 and path.exists()
    assert load_pepper(configured=None, dev_file=path, is_dev=True) == first
