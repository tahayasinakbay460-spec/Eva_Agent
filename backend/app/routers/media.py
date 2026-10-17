"""EVA'nın sesi ve yüzü: katalog, kullanıcının seçimi, hazır seslerin önizlemesi."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser
from app.database import get_db
from app.models.persona import Persona
from app.models.user import User
from app.schemas.media import MediaChoiceOut, MediaOptionOut, MediaOptionsOut, MediaPreferenceIn
from app.services import media_service, persona_service

router = APIRouter(prefix="/media", tags=["media"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
# Önizleme sağlayıcıda ücretli ses üretir: biyometrik uçlarla aynı sıkı sınır.
preview_limit = Depends(rate_limited("media_preview", "rate_limit_biometric_per_minute"))


async def _persona(db: AsyncSession, user: User, persona_id: uuid.UUID | None) -> Persona:
    try:
        return await media_service.persona_for(db, user, persona_id)
    except persona_service.PersonaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Persona not found") from exc


async def _options_out(
    request: Request, db: AsyncSession, user: User, persona: Persona
) -> MediaOptionsOut:
    state = request.app.state
    o = await media_service.options(db, state.settings, state.registry, user, persona)
    return MediaOptionsOut(
        voices=[MediaOptionOut(key=v.key, name=v.name) for v in o.voices],
        avatars=[MediaOptionOut(key=a.key, name=a.name, has_image=a.has_image) for a in o.avatars],
        own_voice=o.own_voice,
        own_avatar=o.own_avatar,
        selected=MediaChoiceOut(voice=o.selected.voice, avatar=o.selected.avatar),
        defaults=MediaChoiceOut(voice=o.defaults.voice, avatar=o.defaults.avatar),
    )


@router.get("/options", response_model=MediaOptionsOut, dependencies=[default_limit])
async def get_options(
    request: Request,
    user: CurrentUser,
    db: DB,
    persona_id: Annotated[uuid.UUID | None, Query()] = None,
) -> MediaOptionsOut:
    return await _options_out(request, db, user, await _persona(db, user, persona_id))


@router.put("/preferences", response_model=MediaOptionsOut, dependencies=[default_limit])
async def set_preferences(
    request: Request, body: MediaPreferenceIn, user: CurrentUser, db: DB
) -> MediaOptionsOut:
    persona = await _persona(db, user, body.persona_id)
    state = request.app.state
    try:
        await media_service.set_preference(
            db, state.settings, state.registry, user, persona, voice=body.voice, avatar=body.avatar
        )
    except media_service.MediaChoiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return await _options_out(request, db, user, persona)


@router.post(
    "/voices/{key}/preview",
    dependencies=[preview_limit],
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}, "description": "WAV audio"}},
)
async def voice_preview(
    request: Request,
    key: str,
    user: CurrentUser,
) -> Response:
    state = request.app.state
    try:
        audio = await media_service.voice_preview(state.settings, state.registry, user, key)
    except media_service.MediaChoiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return Response(
        content=audio, media_type="audio/wav", headers={"Content-Disposition": "inline"}
    )


@router.get(
    "/avatars/{key}/image",
    dependencies=[default_limit],
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}}}},
)
async def avatar_image(request: Request, key: str, user: CurrentUser) -> Response:
    try:
        image = media_service.avatar_image(request.app.state.settings, key)
    except media_service.MediaChoiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return Response(content=image.data, media_type=image.media_type)
