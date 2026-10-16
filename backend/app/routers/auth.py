"""Authentication endpoints.

Passkey sign-up/sign-in (ADR 0002) issue the same opaque session token as before.
``/auth/dev-login`` exists only while ``EVA_ENV`` is dev/test.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser, issue_session, revoke_session
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    DevLoginRequest,
    PasskeyOptionsOut,
    PasskeySignUpRequest,
    PasskeyVerifyRequest,
    TokenOut,
    UserOut,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DB = Annotated[AsyncSession, Depends(get_db)]
AUTH_LIMIT = [Depends(rate_limited("auth", "rate_limit_auth_per_minute"))]


def _auth_failed() -> HTTPException:
    # One body for every failure: callers learn nothing about which check failed.
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification failed")


@router.post("/passkey/register/options", response_model=PasskeyOptionsOut, dependencies=AUTH_LIMIT)
async def passkey_register_options(
    request: Request, body: PasskeySignUpRequest, db: DB
) -> PasskeyOptionsOut:
    form = auth_service.SignUpForm(display_name=body.display_name.strip(), locale=body.locale)
    ceremony = await auth_service.begin_registration(db, request.app.state.settings, form)
    return PasskeyOptionsOut(flow_id=ceremony.flow_id, options=ceremony.options)


@router.post("/passkey/register/verify", response_model=TokenOut, dependencies=AUTH_LIMIT)
async def passkey_register_verify(request: Request, body: PasskeyVerifyRequest, db: DB) -> TokenOut:
    settings = request.app.state.settings
    try:
        user = await auth_service.finish_registration(db, settings, body.flow_id, body.credential)
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    token = await issue_session(db, user, settings.session_ttl_hours)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/passkey/login/options", response_model=PasskeyOptionsOut, dependencies=AUTH_LIMIT)
async def passkey_login_options(request: Request, db: DB) -> PasskeyOptionsOut:
    ceremony = await auth_service.begin_login(db, request.app.state.settings)
    return PasskeyOptionsOut(flow_id=ceremony.flow_id, options=ceremony.options)


@router.post("/passkey/login/verify", response_model=TokenOut, dependencies=AUTH_LIMIT)
async def passkey_login_verify(request: Request, body: PasskeyVerifyRequest, db: DB) -> TokenOut:
    settings = request.app.state.settings
    try:
        user = await auth_service.finish_login(db, settings, body.flow_id, body.credential)
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    token = await issue_session(db, user, settings.session_ttl_hours)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post(
    "/dev-login",
    response_model=TokenOut,
    dependencies=[Depends(rate_limited("auth", "rate_limit_auth_per_minute"))],
)
async def dev_login(request: Request, body: DevLoginRequest, db: DB) -> TokenOut:
    settings = request.app.state.settings
    if not settings.is_dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    result = await db.execute(select(User).where(User.handle == body.handle))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(handle=body.handle, display_name=body.display_name)
        db.add(user)
        await db.commit()
    token = await issue_session(db, user, settings.session_ttl_hours)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, user: CurrentUser, db: DB) -> None:
    await revoke_session(db, request.state.session_token)
