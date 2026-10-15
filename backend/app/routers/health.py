from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: str
    env: str
    version: str


@router.get("/health", response_model=HealthOut)
async def health(request: Request) -> HealthOut:
    return HealthOut(status="ok", env=request.app.state.settings.env, version=__version__)
