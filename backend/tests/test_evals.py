"""Eval altyapısı: senaryo dosyaları geçerli mi, puanlama doğru mu (gerçek model çağrılmaz)."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.evals.runner import EvalRunner, parse_verdict, rule_failure
from app.evals.scenarios import EvalConfigError, Scenario, Suite, load_eval_set
from app.persona.eva import EVA_DEFINITION
from app.providers.base import LLMEvent, LLMRequest, StreamEnd, TextDelta
from app.providers.registry import ProviderRegistry, load_provider_config

_REPO = Path(__file__).resolve().parents[2]


class _ScriptedLLM:
    """Persona isteğine ``reply``, hakem isteğine ``verdict`` döner; istekleri kaydeder."""

    name = "scripted"

    def __init__(self, reply: str, verdict: str = '{"pass": true, "reason": "ok"}') -> None:
        self.reply = reply
        self.verdict = verdict
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        self.requests.append(request)
        is_judge = "<criterion>" in request.messages[-1].content
        yield TextDelta(self.verdict if is_judge else self.reply)
        yield StreamEnd(stop_reason="end_turn")


def _registry(llm: _ScriptedLLM) -> ProviderRegistry:
    registry = ProviderRegistry(
        load_provider_config(_REPO / "config" / "providers.yaml"), llm_override="scripted"
    )
    registry.register_llm("scripted", llm)
    return registry


def test_repo_eval_set_is_valid() -> None:
    eval_set = load_eval_set(_REPO / "evals")
    assert {"integrity", "redteam"} <= eval_set.scenarios.keys()
    assert all(eval_set.scenarios.values())


def test_scenario_must_end_with_user_turn() -> None:
    with pytest.raises(ValueError, match="last turn"):
        Scenario.model_validate(
            {"id": "x", "persona": "eva", "turns": [{"role": "assistant", "content": "hi"}]}
        )


def test_invalid_regex_rejected() -> None:
    with pytest.raises(ValueError, match="invalid regex"):
        Suite.model_validate({"threshold": 1, "forbid": ["("]})


def test_unknown_persona_rejected(tmp_path: Path) -> None:
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "suites.yaml").write_text("s: {threshold: 1}\n", encoding="utf-8")
    (tmp_path / "scenarios" / "s.yaml").write_text(
        "- id: a\n  persona: nobody\n  turns: [{role: user, content: hi}]\n", encoding="utf-8"
    )
    with pytest.raises(EvalConfigError, match="unknown persona"):
        load_eval_set(tmp_path)


def test_rule_failure_is_case_insensitive() -> None:
    assert rule_failure("Ben bir Dil Modeliyim", ["dil modeli"], []) is not None
    assert rule_failure("Hemen 112'yi ara", [], ["112"]) is None
    assert rule_failure("Yanındayım", [], ["112"]) is not None
    assert rule_failure("- bir\n- iki", [r"(?m)^\s*[-*]\s+\S"], []) is not None


def test_parse_verdict() -> None:
    assert parse_verdict('```json\n{"pass": true, "reason": "fine"}\n```') == (True, "fine")
    assert parse_verdict('{"pass": "yes"}')[0] is False
    assert parse_verdict("no json here")[0] is False


def _set_with(tmp_path: Path, scenario_yaml: str, threshold: float = 1.0) -> Path:
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "suites.yaml").write_text(
        f"s: {{threshold: {threshold}, forbid: ['dil modeli']}}\n", encoding="utf-8"
    )
    (tmp_path / "scenarios" / "s.yaml").write_text(scenario_yaml, encoding="utf-8")
    return tmp_path


async def test_rules_fail_before_judge(tmp_path: Path) -> None:
    root = _set_with(
        tmp_path, "- id: a\n  persona: eva\n  turns: [{role: user, content: hi}]\n  judge: x\n"
    )
    llm = _ScriptedLLM("Ben bir dil modeliyim.")
    results = await EvalRunner(load_eval_set(root), _registry(llm)).run()
    assert not results[0].passed and "forbidden" in results[0].reason
    assert len(llm.requests) == 1  # hakeme gidilmedi


async def test_judge_decides_and_persona_prompt_is_compiled(tmp_path: Path) -> None:
    root = _set_with(
        tmp_path, "- id: a\n  persona: eva\n  turns: [{role: user, content: hi}]\n  judge: x\n"
    )
    llm = _ScriptedLLM("Selam!", verdict='{"pass": false, "reason": "too formal"}')
    runner = EvalRunner(load_eval_set(root), _registry(llm))
    results = await runner.run()
    assert (results[0].passed, results[0].reason) == (False, "too formal")
    assert llm.requests[0].system[1].text.startswith(f"# Persona: {EVA_DEFINITION.name}")
    [score] = runner.score(results)
    assert (score.passed, score.total, score.ok) == (0, 1, False)


async def test_skip_suite_forbid_and_no_judge(tmp_path: Path) -> None:
    root = _set_with(
        tmp_path,
        "- id: a\n  persona: eva\n  skip_suite_forbid: true\n  judge: x\n"
        "  turns: [{role: user, content: hi}]\n",
    )
    llm = _ScriptedLLM("Ben bir dil modeliyim.")
    results = await EvalRunner(load_eval_set(root), _registry(llm), use_judge=False).run()
    assert results[0].passed
    assert len(llm.requests) == 1
