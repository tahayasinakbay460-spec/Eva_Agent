"""Application settings.

All values come from environment variables (prefix ``EVA_``) or ``backend/.env``.
Secrets are never defaulted here; provider SDKs read their own keys
(e.g. ``ANTHROPIC_API_KEY``) straight from the environment.
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
    # Force every llm.* feature onto one adapter (tests use "mock").
    llm_provider_override: str | None = None

    session_ttl_hours: int = 24 * 7
    chat_history_turns: int = 20

    # WebAuthn relying party (ADR 0002). The RP ID is the domain passkeys are bound to;
    # changing it in production invalidates every registered passkey.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "EVA"
    webauthn_origins: list[str] = ["http://localhost:3000"]
    auth_challenge_ttl_s: int = 300

    rate_limit_auth_per_minute: int = 10
    rate_limit_chat_per_minute: int = 30
    rate_limit_default_per_minute: int = 120

    # Observability (§3). OTLP endpoint/headers come from the standard OTEL_* env vars.
    otel_enabled: bool = False
    sentry_dsn: str | None = None

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
