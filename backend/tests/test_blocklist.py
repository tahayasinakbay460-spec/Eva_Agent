"""Engel listesi eşleştirmesi: normalize, tam kelime, dosya doğrulaması."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.persona.blocklist import (
    BlocklistConfigError,
    blocklist_for,
    load_blocklist,
    normalize,
)

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


def test_normalize_folds_turkish_and_punctuation() -> None:
    assert normalize("Örümcek-Adam!") == "orumcek adam"
    assert normalize("  Hz. MUHAMMED ") == "hz muhammed"
    assert normalize("İstanbul ŞĞÇ") == "istanbul sgc"


def test_repo_lists_load_and_match_whole_words_only() -> None:
    bl = load_blocklist(
        _REPO_CONFIG / "blocked_franchises.yaml", _REPO_CONFIG / "sensitive_figures.yaml"
    )
    assert bl.check("Batman") is not None
    assert bl.check("Batmanlı") is None
    assert bl.check("Süper Batman Kardeş") is not None
    match = bl.check("hz muhammed")
    assert match is not None and match.category == "sacred"
    assert bl.check("Fatih Sultan Mehmet") is None
    assert bl.check("Kanuni Sultan Süleyman") is None
    assert bl.check("Selahaddin Eyyubi") is None


def test_builtin_names_pass_the_blocklist() -> None:
    from app.persona.builtin import BUILTIN_CHARACTERS

    s = Settings(_env_file=None)
    bl = blocklist_for(s.blocked_franchises_config, s.sensitive_figures_config)
    assert all(bl.check(d.name) is None for d in BUILTIN_CHARACTERS.values())


def test_bad_files_are_rejected(tmp_path: Path) -> None:
    fr, se = tmp_path / "fr.yaml", tmp_path / "se.yaml"
    fr.write_text("terms: [batman]\n", encoding="utf-8")
    se.write_text("unknown: [x]\n", encoding="utf-8")
    with pytest.raises(BlocklistConfigError):
        load_blocklist(fr, se)
    se.write_text('sacred: [""]\n', encoding="utf-8")
    with pytest.raises(BlocklistConfigError):
        load_blocklist(fr, se)


def test_cache_reloads_when_the_file_changes(tmp_path: Path) -> None:
    import os

    fr, se = tmp_path / "fr.yaml", tmp_path / "se.yaml"
    fr.write_text("terms: [batman]\n", encoding="utf-8")
    se.write_text("sacred: []\n", encoding="utf-8")
    assert blocklist_for(fr, se).check("Superman") is None
    fr.write_text("terms: [batman, superman]\n", encoding="utf-8")
    stat = fr.stat()
    os.utime(fr, (stat.st_atime, stat.st_mtime + 5))
    assert blocklist_for(fr, se).check("Superman") is not None
