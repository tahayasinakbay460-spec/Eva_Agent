"""Authentication endpoints.

``/auth/dev-login`` exists only while ``EVA_ENV`` is dev/test. Passkey + MFA (§11.2)
replaces it; the session model and ``get_current_user`` stay as they are.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser, issue_session, revoke_session
from app.database import get_db
from app.models.user import User
from app.schemas.auth import DevLoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

DB = Annotated[AsyncSession, Depends(get_db)]


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
