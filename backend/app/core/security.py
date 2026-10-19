"""Kimlik doğrulamanın temel parçaları: opak bearer token'lar + "giriş yapmış kullanıcı"
bağımlılığı.

Token'lar 256 bitlik rastgele metinlerdir; veritabanında yalnızca SHA-256 özeti tutulur.
Böylece veritabanı sızsa bile kullanılabilir token sızmaz. Passkey/MFA girişi (§11.2) de
aynı türde oturum açacak; değişen yalnızca *giriş* adımı.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, utcnow
from app.models.session import AuthSession
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_session(db: AsyncSession, user: User, ttl_hours: int) -> str:
    """Oturum satırı oluşturur ve düz token'ı döndürür (yalnızca bir kez gösterilir)."""
    token = generate_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(hours=ttl_hours),
        )
    )
    await db.commit()
    return token


async def revoke_session(db: AsyncSession, token: str) -> None:
    result = await db.execute(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    )
    session = result.scalar_one_or_none()
    if session is not None and session.revoked_at is None:
        session.revoked_at = utcnow()
        await db.commit()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    result = await db.execute(
        select(AuthSession).where(AuthSession.token_hash == hash_token(credentials.credentials))
    )
    session = result.scalar_one_or_none()
    now = utcnow()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise _unauthorized()
    request.state.session_token = credentials.credentials
    request.state.auth_session_id = session.id
    user = session.user
    # Vefat sonrası Miras'ın hareketsizlik saati (ADR 0011); uyarı sürecini de durdurur.
    from app.services.legacy_posthumous_service import touch_activity

    await touch_activity(db, user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def step_up_valid_until(session: AuthSession, ttl_s: int) -> datetime | None:
    """Adım-yukarı doğrulamanın bittiği an; hiç yapılmadıysa ya da süresi geçtiyse None."""
    if session.step_up_at is None:
        return None
    until = session.step_up_at + timedelta(seconds=ttl_s)
    return until if until > utcnow() else None


async def current_auth_session(request: Request, db: AsyncSession) -> AuthSession:
    session = await db.get(AuthSession, request.state.auth_session_id, populate_existing=True)
    if session is None:  # pragma: no cover - get_current_user az önce buldu
        raise _unauthorized()
    return session


async def require_step_up(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Hassas işlemler için (§11.2): bu oturumda kimlik yakın zamanda yeniden doğrulanmış
    olmalı. Değilse 403 + ``step_up_required``; istemci doğrulama ekranını açar."""
    session = await current_auth_session(request, db)
    if step_up_valid_until(session, request.app.state.settings.step_up_ttl_s) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="step_up_required")
    return user


SteppedUpUser = Annotated[User, Depends(require_step_up)]


async def require_admin(user: CurrentUser) -> User:
    """Yönetici uçları. Admin değilse uç "yok" sayılır (404): yönetim yüzeyi ele verilmesin."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def require_admin_step_up(
    request: Request, user: AdminUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """Biyometrik dosyalara bakmak ve karar vermek: admin + yakın zamanda adım-yukarı."""
    session = await current_auth_session(request, db)
    if step_up_valid_until(session, request.app.state.settings.step_up_ttl_s) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="step_up_required")
    return user


SteppedUpAdmin = Annotated[User, Depends(require_admin_step_up)]
