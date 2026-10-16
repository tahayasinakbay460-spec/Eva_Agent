"""Ayarlar: göreli yollar backend/ klasörüne göre çözülür, sağlayıcı anahtarları ortama geçer."""

import os
from pathlib import Path

import pytest

from app.core.config import Settings, export_provider_keys

BACKEND = Path(__file__).resolve().parents[1]


def test_relative_sqlite_path_is_anchored_to_backend() -> None:
    s = Settings(_env_file=None, database_url="sqlite+aiosqlite:///./eva_dev.db")
    assert s.database_url == "sqlite+aiosqlite:///" + (BACKEND / "eva_dev.db").as_posix()


def test_relative_config_paths_are_anchored_to_backend() -> None:
    s = Settings(_env_file=None, providers_config=Path("../config/providers.yaml"))
    assert s.providers_config == (BACKEND.parent / "config" / "providers.yaml").resolve()


def test_non_sqlite_urls_are_untouched() -> None:
    url = "postgresql+asyncpg://eva:eva@localhost:5432/eva"
    assert Settings(_env_file=None, database_url=url).database_url == url


def test_provider_keys_are_exported_but_eva_settings_are_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "OPENAI_API_KEY=sk-test\nEVA_ENV=prod\nELEVENLABS_API_KEY=\nLIVEKIT_URL=ws://x\n",
        encoding="utf-8",
    )
    for key in ("OPENAI_API_KEY", "EVA_ENV", "ELEVENLABS_API_KEY", "LIVEKIT_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LIVEKIT_URL", "ws://already-set")

    export_provider_keys(env)

    assert os.environ["OPENAI_API_KEY"] == "sk-test"
    assert "EVA_ENV" not in os.environ, "EVA_ settings are read by Settings, not exported"
    assert "ELEVENLABS_API_KEY" not in os.environ, "empty values are skipped"
    assert os.environ["LIVEKIT_URL"] == "ws://already-set", "real environment wins"


def test_missing_env_file_is_fine(tmp_path: Path) -> None:
    export_provider_keys(tmp_path / "nope.env")
