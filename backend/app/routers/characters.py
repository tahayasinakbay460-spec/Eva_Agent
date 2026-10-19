"""Karakter Stüdyosu uçları (Faz 4, ADR 0009). Yüz görseli ham gövde olarak yüklenir
(biyometrik yüklemeyle aynı yol: boyut sınırı akışta, tür sihirli baytlarla)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser
from app.core.uploads import read_body_limited
from app.database import get_db
from app.models.persona import Persona
from app.models.user import User
from app.schemas.character import CharacterIn, CharacterOut
from app.services import biometric_service, character_service
from app.storage.encrypted import EncryptedStore

router = APIRouter(prefix="/characters", tags=["characters"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
# Görsel çözmek pahalı: biyometrik uçlarla aynı sıkı sınır.
upload_limit = Depends(rate_limited("character_face", "rate_limit_biometric_per_minute"))


def _store(request: Request) -> EncryptedStore:
    store: EncryptedStore = request.app.state.store
    return store


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _raise(exc: character_service.CharacterError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.code)


async def _visible(db: AsyncSession, user: User, character_id: uuid.UUID) -> Persona:
    try:
        return await character_service.get_visible(db, user, character_id)
    except character_service.CharacterNotFoundError as exc:
        raise _not_found() from exc


async def _owned(db: AsyncSession, user: User, character_id: uuid.UUID) -> Persona:
    try:
        return await character_service.get_owned(db, user, character_id)
    except character_service.CharacterNotFoundError as exc:
        raise _not_found() from exc


@router.get("", response_model=list[CharacterOut], dependencies=[default_limit])
async def list_characters(
    request: Request,
    user: CurrentUser,
    db: DB,
    scope: Annotated[Literal["public", "mine"], Query()] = "public",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> list[CharacterOut]:
    if scope == "mine":
        personas = await character_service.list_mine(db, user)
    else:
        personas = await character_service.list_public(db, limit=limit, offset=offset)
    return [character_service.to_out(p, user, request.app.state.settings) for p in personas]


@router.post(
    "",
    response_model=CharacterOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[default_limit],
)
async def create_character(
    request: Request, body: CharacterIn, user: CurrentUser, db: DB
) -> CharacterOut:
    state = request.app.state
    try:
        persona = await character_service.create(db, state.settings, state.registry, user, body)
    except character_service.CharacterError as exc:
        raise _raise(exc) from exc
    return character_service.to_out(persona, user, request.app.state.settings)


@router.get("/{character_id}", response_model=CharacterOut, dependencies=[default_limit])
async def get_character(
    request: Request, character_id: uuid.UUID, user: CurrentUser, db: DB
) -> CharacterOut:
    return character_service.to_out(
        await _visible(db, user, character_id), user, request.app.state.settings
    )


@router.put("/{character_id}", response_model=CharacterOut, dependencies=[default_limit])
async def update_character(
    request: Request, character_id: uuid.UUID, body: CharacterIn, user: CurrentUser, db: DB
) -> CharacterOut:
    persona = await _owned(db, user, character_id)
    state = request.app.state
    try:
        persona = await character_service.update(db, state.settings, state.registry, persona, body)
    except character_service.CharacterError as exc:
        raise _raise(exc) from exc
    return character_service.to_out(persona, user, request.app.state.settings)


@router.delete(
    "/{character_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[default_limit]
)
async def delete_character(
    request: Request, character_id: uuid.UUID, user: CurrentUser, db: DB
) -> Response:
    persona = await _owned(db, user, character_id)
    await character_service.delete(db, _store(request), persona)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{character_id}/face",
    response_model=CharacterOut,
    dependencies=[upload_limit],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                t: {"schema": {"type": "string", "format": "binary"}}
                for t in sorted(biometric_service.IMAGE_TYPES)
            },
        }
    },
)
async def upload_face(
    request: Request,
    character_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    # Kullanıcının beyanı: görseli kullanma hakkı var, görseldeki kişi 18 yaşından büyük.
    rights_confirmed: Annotated[bool, Query()] = False,
) -> CharacterOut:
    persona = await _owned(db, user, character_id)
    if not rights_confirmed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "rights_not_confirmed")
    data = await read_body_limited(request, character_service.FACE_SIZE_LIMIT)
    try:
        await character_service.set_face(
            db,
            _store(request),
            user,
            persona,
            media_type=biometric_service.normalize_media_type(request.headers.get("content-type")),
            data=data,
        )
    except character_service.CharacterError as exc:
        raise _raise(exc) from exc
    return character_service.to_out(persona, user, request.app.state.settings)


@router.delete("/{character_id}/face", response_model=CharacterOut, dependencies=[default_limit])
async def delete_face(
    request: Request, character_id: uuid.UUID, user: CurrentUser, db: DB
) -> CharacterOut:
    persona = await _owned(db, user, character_id)
    await character_service.remove_face(db, _store(request), persona)
    return character_service.to_out(persona, user, request.app.state.settings)


@router.get(
    "/{character_id}/face",
    response_class=Response,
    dependencies=[default_limit],
    responses={200: {"content": {"image/png": {}}}},
)
async def get_face(
    request: Request, character_id: uuid.UUID, user: CurrentUser, db: DB
) -> Response:
    persona = await _visible(db, user, character_id)
    face = await character_service.face(db, _store(request), persona)
    if face is None:
        raise _not_found()
    return Response(
        content=face.data,
        media_type=face.media_type,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
