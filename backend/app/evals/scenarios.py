"""Eval senaryolarının şeması ve YAML'dan okunması.

Dosya düzeni (``evals/``):
  suites.yaml        her takımın eşiği ve tüm senaryolarına uygulanan yasak kalıpları
  personas.yaml      yalnızca eval için tanımlanmış test personaları ("eva" hazır gelir)
  scenarios/*.yaml   senaryolar; dosya adı takım adıdır (integrity.yaml -> "integrity")
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.persona.builtin import BUILTIN_CHARACTERS
from app.persona.eva import EVA_DEFINITION, EVA_SLUG
from app.persona.types import PersonaDefinition


class EvalConfigError(ValueError):
    pass


def _check_patterns(patterns: list[str]) -> list[str]:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
    return patterns


class Suite(BaseModel):
    threshold: float = Field(ge=0, le=1)
    forbid: list[str] = Field(default_factory=list)

    @field_validator("forbid")
    @classmethod
    def _valid_patterns(cls, v: list[str]) -> list[str]:
        return _check_patterns(v)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class Scenario(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    persona: str
    turns: list[Turn] = Field(min_length=1)
    # Cevapta geçmemesi / geçmesi gereken kalıplar (büyük-küçük harf duyarsız).
    forbid: list[str] = Field(default_factory=list)
    require: list[str] = Field(default_factory=list)
    # Takımın ortak yasaklarını bu senaryoda uygulama (ör. samimi soruda "yapay zekâ" serbest).
    skip_suite_forbid: bool = False
    # Hakeme verilen ölçüt: cevap bunu sağlıyorsa geçer.
    judge: str | None = None

    @field_validator("forbid", "require")
    @classmethod
    def _valid_patterns(cls, v: list[str]) -> list[str]:
        return _check_patterns(v)

    @model_validator(mode="after")
    def _last_turn_is_user(self) -> "Scenario":
        if self.turns[-1].role != "user":
            raise ValueError("last turn must be a user turn")
        return self


@dataclass(frozen=True, slots=True)
class EvalSet:
    suites: dict[str, Suite]
    personas: dict[str, PersonaDefinition]
    scenarios: dict[str, list[Scenario]]  # takım adı -> senaryolar


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvalConfigError(f"{path}: {exc}") from exc


def load_eval_set(root: Path) -> EvalSet:
    try:
        suites_raw = _read_yaml(root / "suites.yaml") or {}
        suites = {str(k): Suite.model_validate(v) for k, v in suites_raw.items()}

        # EVA ve hazır karakterler (slug ile) hazır gelir; personas.yaml yalnızca test personaları.
        personas: dict[str, PersonaDefinition] = {EVA_SLUG: EVA_DEFINITION, **BUILTIN_CHARACTERS}
        personas_file = root / "personas.yaml"
        extra = _read_yaml(personas_file) if personas_file.exists() else {}
        for key, value in (extra or {}).items():
            if key in personas:
                raise EvalConfigError(f"personas.yaml: {key!r} is built in")
            personas[str(key)] = PersonaDefinition.model_validate(value)

        scenarios: dict[str, list[Scenario]] = {}
        for path in sorted((root / "scenarios").glob("*.yaml")):
            suite = path.stem
            if suite not in suites:
                raise EvalConfigError(f"{path}: no suite {suite!r} in suites.yaml")
            items = [Scenario.model_validate(s) for s in (_read_yaml(path) or [])]
            scenarios[suite] = items
    except ValueError as exc:  # pydantic.ValidationError da bir ValueError
        if isinstance(exc, EvalConfigError):
            raise
        raise EvalConfigError(str(exc)) from exc

    seen: set[str] = set()
    for suite, items in scenarios.items():
        for scenario in items:
            if scenario.id in seen:
                raise EvalConfigError(f"duplicate scenario id {scenario.id!r}")
            seen.add(scenario.id)
            if scenario.persona not in personas:
                raise EvalConfigError(
                    f"{suite}/{scenario.id}: unknown persona {scenario.persona!r}"
                )
    return EvalSet(suites=suites, personas=personas, scenarios=scenarios)
