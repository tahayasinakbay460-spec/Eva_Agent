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
    CodeFlowOut,
    CodeVerifyRequest,
    DevLoginRequest,
    PasskeyOptionsOut,
    PasskeySignUpRequest,
    PasskeyVerifyRequest,
    PasswordLoginRequest,
    PasswordResetRequest,
    PasswordResetVerifyRequest,
    PasswordSignUpRequest,
    TokenOut,
    UserOut,
)
from app.services import auth_service, password_auth_service

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


# --- email + password, confirmed by an emailed code (threat model §2) -------------


def _password_deps(request: Request) -> password_auth_service.Deps:
    return password_auth_service.Deps(
        messaging=request.app.state.registry.messaging(),
        limiter=request.app.state.rate_limiter,
    )


def _weak_password() -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Weak password")


@router.post(
    "/password/register",
    response_model=CodeFlowOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=AUTH_LIMIT,
)
async def password_register(request: Request, body: PasswordSignUpRequest, db: DB) -> CodeFlowOut:
    form = password_auth_service.SignUpForm(
        email=body.email,
        password=body.password,
        display_name=body.display_name.strip(),
        locale=body.locale,
    )
    try:
        flow_id = await password_auth_service.start_signup(db, _password_deps(request), form)
    except password_auth_service.WeakPasswordError as exc:
        raise _weak_password() from exc
    return CodeFlowOut(flow_id=flow_id)


@router.post("/password/register/verify", response_model=TokenOut, dependencies=AUTH_LIMIT)
async def password_register_verify(request: Request, body: CodeVerifyRequest, db: DB) -> TokenOut:
    try:
        user = await password_auth_service.finish_signup(db, body.flow_id, body.code)
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    token = await issue_session(db, user, request.app.state.settings.session_ttl_hours)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/password/login", response_model=CodeFlowOut, dependencies=AUTH_LIMIT)
async def password_login(request: Request, body: PasswordLoginRequest, db: DB) -> CodeFlowOut:
    try:
        flow_id = await password_auth_service.start_login(
            db, _password_deps(request), body.email, body.password
        )
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    return CodeFlowOut(flow_id=flow_id)


@router.post("/password/login/verify", response_model=TokenOut, dependencies=AUTH_LIMIT)
async def password_login_verify(request: Request, body: CodeVerifyRequest, db: DB) -> TokenOut:
    try:
        user = await password_auth_service.finish_login(db, body.flow_id, body.code)
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    token = await issue_session(db, user, request.app.state.settings.session_ttl_hours)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post(
    "/password/reset",
    response_model=CodeFlowOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=AUTH_LIMIT,
)
async def password_reset(request: Request, body: PasswordResetRequest, db: DB) -> CodeFlowOut:
    flow_id = await password_auth_service.start_reset(
        db, _password_deps(request), body.email, body.locale
    )
    return CodeFlowOut(flow_id=flow_id)


@router.post(
    "/password/reset/verify", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTH_LIMIT
)
async def password_reset_verify(request: Request, body: PasswordResetVerifyRequest, db: DB) -> None:
    """Sets the new password and signs the user out everywhere; they then sign in again."""
    try:
        await password_auth_service.finish_reset(
            db, _password_deps(request), body.flow_id, body.code, body.new_password
        )
    except password_auth_service.WeakPasswordError as exc:
        raise _weak_password() from exc
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
