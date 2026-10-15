"""Loads ``config/providers.yaml`` and hands out adapters per feature."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, get_args

import yaml

from app.providers.anthropic import AnthropicLLMProvider
from app.providers.base import Effort, LLMProvider
from app.providers.mock import MockLLMProvider


@dataclass(frozen=True, slots=True)
class LLMFeatureConfig:
    provider: str
    model: str
    max_tokens: int = 1024
    effort: Effort | None = None


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    llm: dict[str, LLMFeatureConfig]


class ProviderConfigError(ValueError):
    pass


def load_provider_config(path: Path) -> ProviderConfig:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    llm_section = raw.get("llm")
    if not isinstance(llm_section, dict):
        raise ProviderConfigError(f"{path}: missing 'llm' section")

    llm: dict[str, LLMFeatureConfig] = {}
    for feature, item in llm_section.items():
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
    return ProviderConfig(llm=llm)


_LLM_FACTORIES: dict[str, Callable[[], LLMProvider]] = {
    "mock": MockLLMProvider,
    "anthropic": AnthropicLLMProvider,
}


class ProviderRegistry:
    def __init__(self, config: ProviderConfig, *, llm_override: str | None = None) -> None:
        self._config = config
        self._llm_override = llm_override or None
        self._llm_instances: dict[str, LLMProvider] = {}

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
