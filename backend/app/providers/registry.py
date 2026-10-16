"""Loads ``config/providers.yaml`` and hands out adapters per feature."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast, get_args

import yaml

from app.providers.anthropic import AnthropicLLMProvider
from app.providers.base import (
    AvatarEnrollmentProvider,
    AvatarProvider,
    Effort,
    EmbeddingProvider,
    LLMProvider,
    MessagingProvider,
    ModerationProvider,
    STTProvider,
    TTSProvider,
    VoiceEnrollmentProvider,
)
from app.providers.dev_mailbox import DevMailboxMessagingProvider
from app.providers.mock import (
    MockAvatarEnrollmentProvider,
    MockAvatarProvider,
    MockEmbeddingProvider,
    MockLLMProvider,
    MockMessagingProvider,
    MockModerationProvider,
    MockSTTProvider,
    MockTTSProvider,
    MockVoiceEnrollmentProvider,
)

# Non-LLM interfaces, keyed by their section name in providers.yaml.
ProviderKind = Literal[
    "stt",
    "tts",
    "voice_enrollment",
    "avatar",
    "avatar_enrollment",
    "embedding",
    "moderation",
    "messaging",
]


@dataclass(frozen=True, slots=True)
class LLMFeatureConfig:
    provider: str
    model: str
    max_tokens: int = 1024
    effort: Effort | None = None


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    provider: str


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    llm: dict[str, LLMFeatureConfig]
    features: dict[ProviderKind, dict[str, FeatureConfig]]


class ProviderConfigError(ValueError):
    pass


def _parse_llm(section: Any, path: Path) -> dict[str, LLMFeatureConfig]:
    if not isinstance(section, dict):
        raise ProviderConfigError(f"{path}: missing 'llm' section")
    llm: dict[str, LLMFeatureConfig] = {}
    for feature, item in section.items():
        if not isinstance(item, dict) or "provider" not in item or "model" not in item:
            raise ProviderConfigError(f"llm.{feature}: needs 'provider' and 'model'")
        effort = item.get("effort")
        if effort is not None and effort not in get_args(Effort):
            raise ProviderConfigError(f"llm.{feature}.effort: invalid value {effort!r}")
        llm[str(feature)] = LLMFeatureConfig(
            provider=str(item["provider"]),
            model=str(item["model"]),
            max_tokens=int(item.get("max_tokens", 1024)),
            effort=cast(Effort | None, effort),
        )
    return llm


def load_provider_config(path: Path) -> ProviderConfig:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = raw.keys() - {"llm", *get_args(ProviderKind)}
    if unknown:
        raise ProviderConfigError(f"{path}: unknown sections {sorted(unknown)}")

    features: dict[ProviderKind, dict[str, FeatureConfig]] = {}
    for kind in get_args(ProviderKind):
        section = raw.get(kind) or {}
        if not isinstance(section, dict):
            raise ProviderConfigError(f"{kind}: must be a mapping of features")
        parsed: dict[str, FeatureConfig] = {}
        for feature, item in section.items():
            if not isinstance(item, dict) or "provider" not in item:
                raise ProviderConfigError(f"{kind}.{feature}: needs 'provider'")
            parsed[str(feature)] = FeatureConfig(provider=str(item["provider"]))
        features[kind] = parsed
    return ProviderConfig(llm=_parse_llm(raw.get("llm"), path), features=features)


_LLM_FACTORIES: dict[str, Callable[[], LLMProvider]] = {
    "mock": MockLLMProvider,
    "anthropic": AnthropicLLMProvider,
}

# Real adapters are added here as each §15 decision lands; until then only mocks exist.
_FACTORIES: dict[ProviderKind, dict[str, Callable[[], object]]] = {
    "stt": {"mock": MockSTTProvider},
    "tts": {"mock": MockTTSProvider},
    "voice_enrollment": {"mock": MockVoiceEnrollmentProvider},
    "avatar": {"mock": MockAvatarProvider},
    "avatar_enrollment": {"mock": MockAvatarEnrollmentProvider},
    "embedding": {"mock": MockEmbeddingProvider},
    "moderation": {"mock": MockModerationProvider},
    "messaging": {"mock": MockMessagingProvider, "dev_mailbox": DevMailboxMessagingProvider},
}


def registered_adapters(kind: ProviderKind) -> list[str]:
    return sorted(_FACTORIES[kind])


def create_adapter(kind: ProviderKind, name: str) -> object:
    factory = _FACTORIES[kind].get(name)
    if factory is None:
        raise ProviderConfigError(f"unknown {kind} provider {name!r}")
    return factory()


class ProviderRegistry:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        llm_override: str | None = None,
        overrides: dict[ProviderKind, str] | None = None,
    ) -> None:
        self._config = config
        self._llm_override = llm_override or None
        # Force one adapter for every feature of a kind (tests pin messaging to "mock").
        self._overrides = {k: v for k, v in (overrides or {}).items() if v}
        self._llm_instances: dict[str, LLMProvider] = {}
        self._instances: dict[tuple[ProviderKind, str], object] = {}

    def llm(self, feature: str) -> tuple[LLMProvider, LLMFeatureConfig]:
        try:
            feature_cfg = self._config.llm[feature]
        except KeyError as exc:
            raise ProviderConfigError(f"no llm config for feature {feature!r}") from exc
        name = self._llm_override or feature_cfg.provider
        if name not in self._llm_instances:
            factory = _LLM_FACTORIES.get(name)
            if factory is None:
                raise ProviderConfigError(f"unknown llm provider {name!r}")
            self._llm_instances[name] = factory()
        return self._llm_instances[name], feature_cfg

    def register_llm(self, name: str, provider: LLMProvider) -> None:
        """Inject a prebuilt adapter (tests)."""
        self._llm_instances[name] = provider

    def provider_name(self, kind: ProviderKind, feature: str) -> str:
        try:
            configured = self._config.features[kind][feature].provider
        except KeyError as exc:
            raise ProviderConfigError(f"no {kind} config for feature {feature!r}") from exc
        return self._overrides.get(kind, configured)

    def _resolve(self, kind: ProviderKind, feature: str) -> object:
        name = self.provider_name(kind, feature)
        key = (kind, name)
        if key not in self._instances:
            self._instances[key] = create_adapter(kind, name)
        return self._instances[key]

    def stt(self, feature: str) -> STTProvider:
        return cast(STTProvider, self._resolve("stt", feature))

    def tts(self, feature: str) -> TTSProvider:
        return cast(TTSProvider, self._resolve("tts", feature))

    def voice_enrollment(self, feature: str = "default") -> VoiceEnrollmentProvider:
        return cast(VoiceEnrollmentProvider, self._resolve("voice_enrollment", feature))

    def avatar(self, feature: str) -> AvatarProvider:
        return cast(AvatarProvider, self._resolve("avatar", feature))

    def avatar_enrollment(self, feature: str = "default") -> AvatarEnrollmentProvider:
        return cast(AvatarEnrollmentProvider, self._resolve("avatar_enrollment", feature))

    def embedding(self, feature: str) -> EmbeddingProvider:
        return cast(EmbeddingProvider, self._resolve("embedding", feature))

    def moderation(self, feature: str = "default") -> ModerationProvider:
        return cast(ModerationProvider, self._resolve("moderation", feature))

    def messaging(self, feature: str = "default") -> MessagingProvider:
        return cast(MessagingProvider, self._resolve("messaging", feature))
