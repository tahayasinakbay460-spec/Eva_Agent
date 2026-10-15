"""Authentication primitives: opaque bearer tokens + the current-user dependency.

Tokens are 256-bit random strings; the database stores only their SHA-256 digest,
so a database leak does not leak usable tokens. Passkey/MFA login (§11.2) will issue
the same kind of session; only the *login* step changes.
"""

import hashlib
import secrets
from datetime import timedelta
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
    """Create a session row and return the plaintext token (shown once)."""
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
    return session.user


CurrentUser = Annotated[User, Depends(get_current_user)]
