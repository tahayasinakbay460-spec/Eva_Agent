"""Kimlik doğrulama uç noktaları (giriş, kayıt, çıkış).

Passkey ile kayıt/giriş (ADR 0002) de öncekiyle aynı opak oturum token'ını verir.
``/auth/dev-login`` yalnızca ``EVA_ENV`` dev/test iken vardır.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import (
    CurrentUser,
    current_auth_session,
    issue_session,
    revoke_session,
    step_up_valid_until,
)
from app.database import get_db, utcnow
from app.models.auth import Passkey
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
    StepUpPasswordRequest,
    StepUpStatusOut,
    TokenOut,
    UserOut,
)
from app.services import auth_service, password_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DB = Annotated[AsyncSession, Depends(get_db)]
AUTH_LIMIT = [Depends(rate_limited("auth", "rate_limit_auth_per_minute"))]


def _auth_failed() -> HTTPException:
    # Her hatada aynı cevap: saldırgan hangi kontrolün tutmadığını öğrenemez.
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


# --- e-posta + şifre, e-postayla gelen kodla onaylanır (tehdit modeli §2) ----------


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
    """Yeni şifreyi kaydeder ve kullanıcıyı her cihazdan çıkarır; sonra yeniden giriş yapar."""
    try:
        await password_auth_service.finish_reset(
            db, _password_deps(request), body.flow_id, body.code, body.new_password
        )
    except password_auth_service.WeakPasswordError as exc:
        raise _weak_password() from exc
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc


# --- adım-yukarı doğrulama (§11.2) ------------------------------------------------
# Hassas işlemden önce (ses/yüz kaydı, rıza değişikliği, Miras anahtarı...) kullanıcı bu
# oturumda kimliğini yeniden doğrular. Başarılı olunca oturuma bir zaman damgası yazılır;
# ``require_step_up`` bağımlılığı o damganın taze olmasını ister.


async def _step_up_status(request: Request, user: User, db: AsyncSession) -> StepUpStatusOut:
    session = await current_auth_session(request, db)
    has_passkey = await db.scalar(select(Passkey.id).where(Passkey.user_id == user.id).limit(1))
    methods: list[Literal["passkey", "password"]] = []
    if has_passkey is not None:
        methods.append("passkey")
    if user.email is not None and user.password_hash is not None:
        methods.append("password")
    return StepUpStatusOut(
        valid_until=step_up_valid_until(session, request.app.state.settings.step_up_ttl_s),
        methods=methods,
    )


async def _mark_stepped_up(request: Request, user: User, db: AsyncSession) -> StepUpStatusOut:
    session = await current_auth_session(request, db)
    session.step_up_at = utcnow()
    await db.commit()
    return await _step_up_status(request, user, db)


@router.get("/step-up", response_model=StepUpStatusOut)
async def step_up_status(request: Request, user: CurrentUser, db: DB) -> StepUpStatusOut:
    return await _step_up_status(request, user, db)


@router.post("/step-up/passkey/options", response_model=PasskeyOptionsOut, dependencies=AUTH_LIMIT)
async def step_up_passkey_options(request: Request, user: CurrentUser, db: DB) -> PasskeyOptionsOut:
    try:
        ceremony = await auth_service.begin_step_up(db, request.app.state.settings, user)
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    return PasskeyOptionsOut(flow_id=ceremony.flow_id, options=ceremony.options)


@router.post("/step-up/passkey/verify", response_model=StepUpStatusOut, dependencies=AUTH_LIMIT)
async def step_up_passkey_verify(
    request: Request, body: PasskeyVerifyRequest, user: CurrentUser, db: DB
) -> StepUpStatusOut:
    try:
        await auth_service.finish_step_up(
            db, request.app.state.settings, user, body.flow_id, body.credential
        )
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    return await _mark_stepped_up(request, user, db)


@router.post("/step-up/password", response_model=CodeFlowOut, dependencies=AUTH_LIMIT)
async def step_up_password(
    request: Request, body: StepUpPasswordRequest, user: CurrentUser, db: DB
) -> CodeFlowOut:
    try:
        flow_id = await password_auth_service.start_step_up(
            db, _password_deps(request), user, body.password
        )
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    return CodeFlowOut(flow_id=flow_id)


@router.post("/step-up/password/verify", response_model=StepUpStatusOut, dependencies=AUTH_LIMIT)
async def step_up_password_verify(
    request: Request, body: CodeVerifyRequest, user: CurrentUser, db: DB
) -> StepUpStatusOut:
    try:
        await password_auth_service.finish_step_up(db, user, body.flow_id, body.code)
    except auth_service.AuthFailedError as exc:
        raise _auth_failed() from exc
    return await _mark_stepped_up(request, user, db)
