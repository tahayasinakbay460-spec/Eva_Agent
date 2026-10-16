"""Uygulama ayarları.

Tüm değerler ortam değişkenlerinden (``EVA_`` önekli) ya da ``backend/.env`` dosyasından gelir.
Sırlara burada asla varsayılan değer verilmez; sağlayıcı SDK'ları kendi anahtarlarını
(ör. ``ANTHROPIC_API_KEY``) doğrudan ortamdan okur.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "staging", "prod"]

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "dev"
    database_url: str = "sqlite+aiosqlite:///./eva_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]

    providers_config: Path = _REPO_ROOT / "config" / "providers.yaml"
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

    # Arka plan işçisi API'nin içinde de çalışsın mı (ADR 0003)? Boşsa: sadece EVA_ENV=dev iken.
    worker_inprocess: bool | None = None

    # Gözlemlenebilirlik (§3). OTLP adresi/başlıkları standart OTEL_* ortam değişkenlerinden gelir.
    otel_enabled: bool = False
    sentry_dsn: str | None = None

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "test")

    @property
    def run_worker_inprocess(self) -> bool:
        if self.worker_inprocess is not None:
            return self.worker_inprocess
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
