"""Persona tanımı ve ilişki durumu (CLAUDE.md §5.2, §9.2)."""

from typing import Literal

from pydantic import BaseModel, Field

PersonaKind = Literal["eva", "character", "legacy"]
TimeAwareness = Literal["in_era", "aware_of_present"]
RelationshipStage = Literal["introduction", "acquaintance", "close", "best_friend"]


class ExampleDialog(BaseModel):
    user: str = Field(max_length=500)
    persona: str = Field(max_length=1000)


class PersonaDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: PersonaKind
    # "system": biz yazdık (EVA). "user": bir kullanıcı yazdı -> güvenilmez veri bloğu.
    source: Literal["system", "user"] = "user"
    identity: str = Field(max_length=2000)
    personality: str = Field(max_length=4000)
    speaking_style: str = Field(max_length=4000)
    example_dialogs: list[ExampleDialog] = Field(default_factory=list, max_length=10)
    canon_memories: list[str] = Field(default_factory=list, max_length=200)
    time_awareness: TimeAwareness = "aware_of_present"
    language: str = "tr"


class RelationshipState(BaseModel):
    stage: RelationshipStage = "introduction"
    user_display_name: str | None = None
