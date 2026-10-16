"""Her LLMProvider adaptörünün geçmesi gereken sözleşme testleri; burada sahte (mock)
adaptör üzerinde koşar.

Sözleşme testi: arayüzü uygulayan her adaptörün aynı kurallara uyduğunu kontrol eden
ortak test paketi.
"""

from pathlib import Path

import pytest

from app.providers.base import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    StreamEnd,
    SystemBlock,
    TextDelta,
)
from app.providers.mock import MockLLMProvider
from app.providers.registry import ProviderConfigError, ProviderRegistry, load_provider_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def _request() -> LLMRequest:
    return LLMRequest(
        model="test-model",
        system=(SystemBlock("rules", cacheable=True), SystemBlock("dynamic")),
        messages=(LLMMessage("user", "merhaba"),),
        max_tokens=64,
    )


async def assert_llm_contract(provider: LLMProvider) -> str:
    events = [e async for e in provider.stream(_request())]
    assert events, "stream yielded nothing"
    assert all(isinstance(e, TextDelta) for e in events[:-1])
    assert isinstance(events[-1], StreamEnd), "stream must end with exactly one StreamEnd"
    assert sum(isinstance(e, StreamEnd) for e in events) == 1
    return "".join(e.text for e in events[:-1] if isinstance(e, TextDelta))


async def test_mock_provider_contract() -> None:
    text = await assert_llm_contract(MockLLMProvider())
    assert "merhaba" in text


async def test_mock_provider_fixed_reply() -> None:
    text = await assert_llm_contract(MockLLMProvider(reply="sabit cevap"))
    assert text == "sabit cevap"


def test_repo_provider_config_loads() -> None:
    cfg = load_provider_config(REPO_ROOT / "config" / "providers.yaml")
    assert {"chat", "realtime", "background"} <= cfg.llm.keys()
    assert cfg.llm["chat"].provider == "openai"


def test_registry_override_forces_mock() -> None:
    cfg = load_provider_config(REPO_ROOT / "config" / "providers.yaml")
    registry = ProviderRegistry(cfg, llm_override="mock")
    provider, feature = registry.llm("chat")
    assert provider.name == "mock"
    assert feature.model == cfg.llm["chat"].model


def test_registry_rejects_unknown_feature_and_provider(tmp_path: Path) -> None:
    cfg = load_provider_config(REPO_ROOT / "config" / "providers.yaml")
    with pytest.raises(ProviderConfigError):
        ProviderRegistry(cfg, llm_override="mock").llm("nope")
    with pytest.raises(ProviderConfigError):
        ProviderRegistry(cfg, llm_override="nonexistent").llm("chat")

    bad = tmp_path / "p.yaml"
    bad.write_text("llm:\n  chat: {provider: mock, model: m, effort: extreme}\n", encoding="utf-8")
    with pytest.raises(ProviderConfigError):
        load_provider_config(bad)
