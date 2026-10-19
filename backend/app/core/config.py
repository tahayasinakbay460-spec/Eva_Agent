"""Uygulama ayarları.

Tüm değerler ortam değişkenlerinden (``EVA_`` önekli) ya da ``backend/.env`` dosyasından gelir.
Sırlara burada asla varsayılan değer verilmez; sağlayıcı SDK'ları kendi anahtarlarını
(ör. ``OPENAI_API_KEY``) doğrudan ortamdan okur — ``get_settings`` bu yüzden ``.env``'deki
sağlayıcı anahtarlarını süreç ortamına da koyar.

Göreli yollar (``./eva_dev.db``, ``../config/...``) her zaman ``backend/`` klasörüne göre
çözülür; böylece API, işçi ve ``realtime/`` ajanı nereden çalıştırılırsa çalıştırılsın aynı
veritabanını ve ayarları görür.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "staging", "prod"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVA_",
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    env: Environment = "dev"
    database_url: str = "sqlite+aiosqlite:///./eva_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite_path(cls, value: str) -> str:
        prefix = "sqlite+aiosqlite:///"
        if value.startswith(prefix) and not value.endswith(":memory:"):
            path = Path(value[len(prefix) :])
            if not path.is_absolute():
                return prefix + (_BACKEND_ROOT / path).resolve().as_posix()
        return value

    @field_validator(
        "providers_config",
        "media_config",
        "storage_dir",
        "dev_master_key_file",
        "dev_legacy_pepper_file",
        mode="after",
    )
    @classmethod
    def _anchor_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (_BACKEND_ROOT / value).resolve()

    providers_config: Path = _REPO_ROOT / "config" / "providers.yaml"
    media_config: Path = _REPO_ROOT / "config" / "media.yaml"
    # Tüm llm.* özelliklerini tek bir adaptöre zorlar (testler "mock" kullanır).
    llm_provider_override: str | None = None
    # E-posta/SMS adaptörünü zorlar (testler "mock" kullanır; dev varsayılanı providers.yaml'da).
    messaging_provider_override: str | None = None

    session_ttl_hours: int = 24 * 7
    # Sohbet bu kadar saniye sessiz kalınca konuşmadan anı çıkarılır (§6.2).
    memory_extract_idle_s: int = 600
    chat_history_turns: int = 20

    # WebAuthn "relying party" = passkey'lerin güvendiği site, yani biz (ADR 0002). RP ID,
    # passkey'lerin bağlandığı alan adıdır; prod'da değişirse kayıtlı tüm passkey'ler bozulur.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "EVA"
    webauthn_origins: list[str] = ["http://localhost:3000"]
    auth_challenge_ttl_s: int = 300
    # Adım-yukarı doğrulama (§11.2) bu kadar saniye geçerli, sonra yeniden sorulur.
    step_up_ttl_s: int = 600

    rate_limit_auth_per_minute: int = 10
    rate_limit_chat_per_minute: int = 30
    rate_limit_default_per_minute: int = 120

    # Şifreli dosya deposu (§11.3). Lokalde bir klasör; ana anahtar dev'de yerel dosyada durur.
    # Staging/prod'da yerel ana anahtar kabul edilmez, KMS gerekir (KMS_KEY_ID).
    storage_dir: Path = _BACKEND_ROOT / "storage"
    dev_master_key_file: Path = _BACKEND_ROOT / ".dev_master_key"

    # Miras (ADR 0010). Anahtar özetlerinin "biberi": dev'de yerel dosya, staging/prod'da
    # secret manager'dan EVA_LEGACY_KEY_PEPPER (base64, 32 bayt) zorunlu.
    legacy_key_pepper: SecretStr | None = None
    dev_legacy_pepper_file: Path = _BACKEND_ROOT / ".dev_legacy_pepper"
    legacy_key_ttl_days: int = 30
    # E-postalardaki bağlantılar yalnızca kendi alan adımıza gider (§8.3).
    web_url: str = "http://localhost:3000"
    legacy_max_grants: int = 5
    legacy_redeem_max_failures: int = 5
    legacy_redeem_lockout_s: int = 24 * 3600

    # Sesli/görüntülü görüşme (LiveKit, §4.3). Anahtarlar sağlayıcı adlarıyla, öneksiz okunur.
    # Lokal deneme: `livekit-server --dev` -> ws://localhost:7880, anahtar devkey / secret.
    livekit_url: str | None = Field(
        default=None, validation_alias=AliasChoices("LIVEKIT_URL", "EVA_LIVEKIT_URL")
    )
    livekit_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("LIVEKIT_API_KEY", "EVA_LIVEKIT_API_KEY")
    )
    livekit_api_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LIVEKIT_API_SECRET", "EVA_LIVEKIT_API_SECRET"),
    )
    voice_agent_name: str = "eva-voice"
    # Görüşme token'ı sadece odaya girişi açar; kısa ömürlü olsun.
    call_token_ttl_s: int = 120
    # Sahibin kararı (2026-10-16): görüntülü görüşme en fazla 10 dk, 60 sn sessizlikte kapanır,
    # kullanıcı başına günde 30 dk. Sesli görüşme avatar kadar pahalı değil; 30 dk sınır.
    voice_max_duration_s: int = 1800
    video_max_duration_s: int = 600
    call_idle_timeout_s: int = 60
    video_daily_quota_s: int = 1800
    rate_limit_call_per_minute: int = 5
    rate_limit_biometric_per_minute: int = 30

    # Arka plan işçisi API'nin içinde de çalışsın mı (ADR 0003)? Boşsa: sadece EVA_ENV=dev iken.
    worker_inprocess: bool | None = None

    # Gözlemlenebilirlik (§3). OTLP adresi/başlıkları standart OTEL_* ortam değişkenlerinden gelir.
    otel_enabled: bool = False
    sentry_dsn: str | None = None

    @property
    def voice_configured(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "test")

    @property
    def run_worker_inprocess(self) -> bool:
        if self.worker_inprocess is not None:
            return self.worker_inprocess
        return self.env == "dev"


def export_provider_keys(env_file: Path = _BACKEND_ROOT / ".env") -> None:
    """``.env``'deki sağlayıcı anahtarlarını (``EVA_`` öneki olmayanlar, ör. OPENAI_API_KEY)
    süreç ortamına koyar; SDK'lar anahtarı oradan okur. Ortamda zaten olan değer ezilmez."""
    if not env_file.exists():
        return
    for key, value in dotenv_values(env_file).items():
        if value and not key.startswith("EVA_") and key not in os.environ:
            os.environ[key] = value


@lru_cache
def get_settings() -> Settings:
    export_provider_keys()
    return Settings()
