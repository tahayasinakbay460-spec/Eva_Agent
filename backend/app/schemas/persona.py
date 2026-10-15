import uuid

from pydantic import BaseModel, ConfigDict


class PersonaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    name: str
    slug: str | None
