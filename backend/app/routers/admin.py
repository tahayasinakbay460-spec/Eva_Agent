"""Yönetici uçları: biyometrik kayıtların elle incelenmesi (Faz 3; sahibin kararı: yüz
eşleştirme / yaş tahmini sağlayıcısı yok, her kayıt bir insan tarafından onaylanır).

Admin olmayan için bu uçlar "yok"tur (404). Dosyaya bakmak ve karar vermek ayrıca
adım-yukarı doğrulama ister; her dosya açılışı denetim kaydına yazılır."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import AdminUser, SteppedUpAdmin
from app.database import get_db
from app.models.user import User
from app.routers.biometrics import enrollment_out
from app.schemas.biometric import AdminEnrollmentOut, ApproveRequest, RejectRequest
from app.services import biometric_service

router = APIRouter(prefix="/admin", tags=["admin"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))


async def _admin_out(db: AsyncSession, enrollment_id: uuid.UUID) -> AdminEnrollmentOut:
    try:
        enrollment = await biometric_service.get_any(db, enrollment_id)
    except biometric_service.EnrollmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
    owner = await db.get(User, enrollment.user_id)
    if owner is None:  # pragma: no cover - FK cascade
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    base = await enrollment_out(db, enrollment, owner)
    return AdminEnrollmentOut(
        **base.model_dump(), user_id=owner.id, user_display_name=owner.display_name
    )


@router.get(
    "/biometrics/pending", response_model=list[AdminEnrollmentOut], dependencies=[default_limit]
)
async def pending(admin: AdminUser, db: DB) -> list[AdminEnrollmentOut]:
    items = await biometric_service.pending_reviews(db)
    return [await _admin_out(db, e.id) for e in items]


@router.get(
    "/biometrics/enrollments/{enrollment_id}",
    response_model=AdminEnrollmentOut,
    dependencies=[default_limit],
)
async def detail(enrollment_id: uuid.UUID, admin: AdminUser, db: DB) -> AdminEnrollmentOut:
    return await _admin_out(db, enrollment_id)


@router.get(
    "/biometrics/enrollments/{enrollment_id}/files/{file_id}",
    dependencies=[default_limit],
    response_class=Response,
    responses={200: {"content": {"video/webm": {}, "audio/webm": {}}, "description": "media"}},
)
async def file_content(
    request: Request,
    enrollment_id: uuid.UUID,
    file_id: uuid.UUID,
    admin: SteppedUpAdmin,
    db: DB,
) -> Response:
    try:
        enrollment = await biometric_service.get_any(db, enrollment_id)
        data, media_type = await biometric_service.read_file_for_review(
            db, request.app.state.store, admin, enrollment, file_id
        )
    except biometric_service.EnrollmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": "inline"},  # no-store: middleware her cevaba ekler
    )


@router.post(
    "/biometrics/enrollments/{enrollment_id}/approve",
    response_model=AdminEnrollmentOut,
    dependencies=[default_limit],
)
async def approve(
    request: Request,
    enrollment_id: uuid.UUID,
    body: ApproveRequest,
    admin: SteppedUpAdmin,
    db: DB,
) -> AdminEnrollmentOut:
    try:
        enrollment = await biometric_service.get_any(db, enrollment_id)
        await biometric_service.approve(db, request.app.state.settings, admin, enrollment)
    except biometric_service.EnrollmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
    except biometric_service.BiometricError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return await _admin_out(db, enrollment_id)


@router.post(
    "/biometrics/enrollments/{enrollment_id}/reject",
    response_model=AdminEnrollmentOut,
    dependencies=[default_limit],
)
async def reject(
    request: Request,
    enrollment_id: uuid.UUID,
    body: RejectRequest,
    admin: SteppedUpAdmin,
    db: DB,
) -> AdminEnrollmentOut:
    try:
        enrollment = await biometric_service.get_any(db, enrollment_id)
        await biometric_service.reject(
            db, request.app.state.settings, admin, enrollment, body.reason
        )
    except biometric_service.EnrollmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
    except biometric_service.BiometricError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return await _admin_out(db, enrollment_id)
