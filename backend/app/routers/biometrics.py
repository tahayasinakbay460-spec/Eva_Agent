"""Rızalı ses/yüz kaydı uç noktaları (Faz 3). Başlatma, gönderme ve geri alma adım-yukarı
doğrulama ister (§11.2). Dosyalar ham gövde olarak yüklenir (multipart değil): boyut sınırı
akış sırasında uygulanır, tür sihirli baytlarla doğrulanır."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser, SteppedUpUser
from app.database import get_db
from app.models.biometric import BiometricEnrollment
from app.models.user import User
from app.schemas.biometric import (
    ConsentTextOut,
    EnrollmentCreate,
    EnrollmentFileOut,
    EnrollmentOut,
    PreviewRequest,
)
from app.services import biometric_service, consent_texts
from app.storage.encrypted import EncryptedStore

router = APIRouter(prefix="/biometrics", tags=["biometrics"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
biometric_limit = Depends(rate_limited("biometric", "rate_limit_biometric_per_minute"))

ERROR_RESPONSES: dict[int | str, dict[str, str]] = {
    403: {"description": "step_up_required"},
    409: {"description": "state conflict (code in detail)"},
}


def _store(request: Request) -> EncryptedStore:
    store: EncryptedStore = request.app.state.store
    return store


def _raise(exc: biometric_service.BiometricError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.code)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


async def _owned(db: AsyncSession, user: User, enrollment_id: uuid.UUID) -> BiometricEnrollment:
    try:
        return await biometric_service.get_for_user(db, user, enrollment_id)
    except biometric_service.EnrollmentNotFoundError as exc:
        raise _not_found() from exc


async def enrollment_out(
    db: AsyncSession, enrollment: BiometricEnrollment, owner: User
) -> EnrollmentOut:
    v = await biometric_service.view(db, enrollment, owner)
    e = v.enrollment
    return EnrollmentOut(
        id=e.id,
        kind="face" if e.kind == "face" else "voice",
        status=e.status,
        consent_sentence=v.consent_sentence,
        challenge_code=e.challenge_code,
        files=[EnrollmentFileOut.model_validate(f) for f in v.files],
        created_at=e.created_at,
        submitted_at=e.submitted_at,
        activated_at=e.activated_at,
        revoked_at=e.revoked_at,
        reject_reason=e.reject_reason,
    )


@router.get("/consent-text", response_model=ConsentTextOut, dependencies=[default_limit])
async def consent_text(user: CurrentUser, kind: Literal["voice", "face"]) -> ConsentTextOut:
    return ConsentTextOut(
        kind=kind,
        version=consent_texts.VERSION,
        summary=consent_texts.summary(kind, user.locale),
        reading_passage=(
            consent_texts.READING_PASSAGE["en" if user.locale == "en" else "tr"]
            if kind == "voice"
            else None
        ),
    )


@router.get("/enrollments", response_model=list[EnrollmentOut], dependencies=[default_limit])
async def list_enrollments(user: CurrentUser, db: DB) -> list[EnrollmentOut]:
    items = await biometric_service.list_for_user(db, user)
    return [await enrollment_out(db, e, user) for e in items]


@router.post(
    "/enrollments",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[biometric_limit],
    responses=ERROR_RESPONSES,
)
async def start_enrollment(
    request: Request, body: EnrollmentCreate, user: SteppedUpUser, db: DB
) -> EnrollmentOut:
    try:
        enrollment = await biometric_service.start(
            db,
            request.app.state.settings,
            request.app.state.registry,
            user,
            kind=body.kind,
            accepted_version=body.consent_text_version,
        )
    except biometric_service.BiometricError as exc:
        raise _raise(exc) from exc
    return await enrollment_out(db, enrollment, user)


@router.get(
    "/enrollments/{enrollment_id}", response_model=EnrollmentOut, dependencies=[default_limit]
)
async def get_enrollment(enrollment_id: uuid.UUID, user: CurrentUser, db: DB) -> EnrollmentOut:
    return await enrollment_out(db, await _owned(db, user, enrollment_id), user)


async def _read_body(request: Request, limit: int) -> bytes:
    """İstek gövdesini okur; sınır aşılırsa hemen keser (dosyanın tamamını belleğe almadan)."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large")
    return bytes(data)


@router.post(
    "/enrollments/{enrollment_id}/files",
    response_model=EnrollmentFileOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[biometric_limit],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                t: {"schema": {"type": "string", "format": "binary"}}
                for t in (
                    "audio/webm",
                    "audio/ogg",
                    "audio/mp4",
                    "video/webm",
                    "video/mp4",
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                )
            },
        }
    },
)
async def upload_file(
    request: Request,
    enrollment_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    role: Annotated[Literal["sample", "consent_recording"], Query()],
    duration_s: Annotated[int | None, Query(ge=1, le=900)] = None,
) -> EnrollmentFileOut:
    enrollment = await _owned(db, user, enrollment_id)
    kind: biometric_service.Kind = "face" if enrollment.kind == "face" else "voice"
    data = await _read_body(request, biometric_service.SIZE_LIMITS[(kind, role)])
    try:
        sample = await biometric_service.add_file(
            db,
            _store(request),
            user,
            enrollment,
            role=role,
            media_type=biometric_service.normalize_media_type(request.headers.get("content-type")),
            data=data,
            duration_s=duration_s,
        )
    except biometric_service.BiometricError as exc:
        raise _raise(exc) from exc
    return EnrollmentFileOut.model_validate(sample)


@router.delete(
    "/enrollments/{enrollment_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[biometric_limit],
)
async def delete_file(
    request: Request, enrollment_id: uuid.UUID, file_id: uuid.UUID, user: CurrentUser, db: DB
) -> None:
    enrollment = await _owned(db, user, enrollment_id)
    try:
        await biometric_service.delete_file(db, _store(request), enrollment, file_id)
    except biometric_service.EnrollmentNotFoundError as exc:
        raise _not_found() from exc
    except biometric_service.BiometricError as exc:
        raise _raise(exc) from exc


@router.post(
    "/enrollments/{enrollment_id}/submit",
    response_model=EnrollmentOut,
    dependencies=[biometric_limit],
    responses=ERROR_RESPONSES,
)
async def submit(enrollment_id: uuid.UUID, user: SteppedUpUser, db: DB) -> EnrollmentOut:
    enrollment = await _owned(db, user, enrollment_id)
    try:
        await biometric_service.submit(db, user, enrollment)
    except biometric_service.BiometricError as exc:
        raise _raise(exc) from exc
    return await enrollment_out(db, enrollment, user)


@router.post(
    "/enrollments/{enrollment_id}/revoke",
    response_model=EnrollmentOut,
    dependencies=[biometric_limit],
    responses=ERROR_RESPONSES,
)
async def revoke(enrollment_id: uuid.UUID, user: SteppedUpUser, db: DB) -> EnrollmentOut:
    """Rızayı geri alır: kullanım hemen durur, klon ve dosyalar arka planda silinir."""
    enrollment = await _owned(db, user, enrollment_id)
    await biometric_service.revoke(db, user, enrollment)
    return await enrollment_out(db, enrollment, user)


@router.get("/voice/preview-sentences", response_model=list[str], dependencies=[default_limit])
async def preview_sentences(user: CurrentUser) -> list[str]:
    return list(consent_texts.PREVIEW_SENTENCES["en" if user.locale == "en" else "tr"])


@router.post(
    "/voice/preview",
    dependencies=[biometric_limit],
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}, "description": "WAV audio"}},
)
async def voice_preview(
    request: Request, body: PreviewRequest, user: CurrentUser, db: DB
) -> Response:
    """Kendi klon sesinle sabit bir cümle (serbest metin yok, §11.3)."""
    try:
        audio = await biometric_service.voice_preview(
            db, request.app.state.registry, user, body.sentence
        )
    except biometric_service.BiometricError as exc:
        raise _raise(exc) from exc
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline"},  # no-store: middleware her cevaba ekler
    )
