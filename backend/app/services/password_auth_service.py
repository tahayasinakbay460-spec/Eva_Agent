"""Email + password sign-up, sign-in and reset, each confirmed by an emailed code.

See docs/threat-model.md §2. The shape of every flow is the same:

1. ``start_*`` checks what it can, stores a hashed 6-digit code bound to a new flow
   id, emails the code and returns the flow id.
2. ``finish_*`` checks the code (attempt-limited, single use) and completes the flow.

Sign-up and reset answer identically whether or not the email has an account, and
sign-in has one error for "unknown email" and "wrong password" (with equal timing),
so none of them reveal who is registered. Every failure raises ``AuthFailedError``.
"""

import asyncio
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import RateLimiter
from app.database import utcnow
from app.models.auth import AuthCode
from app.models.session import AuthSession
from app.models.user import User
from app.providers.base import MessageTemplate, MessagingProvider, OutboundMessage
from app.services.auth_service import AuthFailedError

Purpose = Literal["signup", "login", "reset"]

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
# Per-email send limit against mail bombing (on top of per-IP request limits).
MAIL_LIMIT = 5
MAIL_WINDOW_S = 600.0

_hasher = PasswordHasher()  # Argon2id, RFC 9106 parameters (argon2-cffi defaults)
_dummy_hash: str | None = None


@dataclass(frozen=True, slots=True)
class SignUpForm:
    email: str
    password: str
    display_name: str
    locale: str


@dataclass(frozen=True, slots=True)
class Deps:
    messaging: MessagingProvider
    limiter: RateLimiter


class WeakPasswordError(ValueError):
    """The password breaks the policy; safe to tell the user (says nothing about accounts)."""


# --- password hashing --------------------------------------------------------------


def check_password_policy(password: str, email: str) -> None:
    if not 10 <= len(password) <= 128:
        raise WeakPasswordError("length")
    if password.strip().casefold() == email.casefold():
        raise WeakPasswordError("equals_email")


async def hash_password(password: str) -> str:
    # Argon2 is deliberately slow (~50 ms, 64 MiB); keep it off the event loop.
    return await asyncio.to_thread(_hasher.hash, password)


async def _verify_password(stored_hash: str, password: str) -> bool:
    def verify() -> bool:
        try:
            return _hasher.verify(stored_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    return await asyncio.to_thread(verify)


async def _dummy() -> str:
    """A real Argon2 hash to verify against when the email is unknown (equal timing)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = await hash_password(secrets.token_urlsafe(16))
    return _dummy_hash


# --- codes ------------------------------------------------------------------------


def _digest(flow_id: uuid.UUID, code: str) -> str:
    return hashlib.sha256(f"{flow_id}:{code}".encode()).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _issue(
    db: AsyncSession,
    deps: Deps,
    *,
    purpose: Purpose,
    email: str,
    locale: str,
    user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    template: MessageTemplate | None,
) -> uuid.UUID:
    """Store a fresh code (older open codes for the same email+purpose die) and send it.

    ``template=None`` creates a decoy flow that can never succeed (unknown email).
    """
    now = utcnow()
    await db.execute(
        update(AuthCode)
        .where(
            AuthCode.email == email,
            AuthCode.purpose == purpose,
            AuthCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    flow_id = uuid.uuid4()
    code = _new_code()
    db.add(
        AuthCode(
            id=flow_id,
            purpose=purpose,
            email=email,
            user_id=user_id,
            # Decoy flows store a digest of nothing anyone was sent.
            code_hash=_digest(flow_id, code if template else secrets.token_hex(16)),
            payload=payload or {},
            created_at=now,
            expires_at=now + CODE_TTL,
        )
    )
    await db.commit()
    if template is not None:
        await _send(deps, email=email, locale=locale, template=template, params={"code": code})
    return flow_id


async def _send(
    deps: Deps,
    *,
    email: str,
    locale: str,
    template: MessageTemplate,
    params: dict[str, str] | None = None,
    limited: bool = True,
) -> None:
    # Anything an anonymous caller can trigger is capped per address; notices that need
    # a valid code first (password changed) are not, so they never crowd out real codes.
    if limited and not await deps.limiter.hit(f"mail:{email}", MAIL_LIMIT, MAIL_WINDOW_S):
        return  # silently skipped: the response must not differ
    await deps.messaging.send(
        OutboundMessage(
            channel="email", to=email, template=template, locale=locale, params=params or {}
        )
    )


async def _check(db: AsyncSession, flow_id: uuid.UUID, purpose: Purpose, code: str) -> AuthCode:
    now = utcnow()
    open_flow = (
        AuthCode.id == flow_id,
        AuthCode.purpose == purpose,
        AuthCode.consumed_at.is_(None),
        AuthCode.expires_at > now,
    )
    # Count the attempt first, atomically, so parallel guesses cannot exceed the cap.
    counted = await db.execute(
        update(AuthCode)
        .where(*open_flow, AuthCode.attempts < MAX_ATTEMPTS)
        .values(attempts=AuthCode.attempts + 1)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if counted.rowcount != 1:  # type: ignore[attr-defined]
        raise AuthFailedError("unknown, expired, used, exhausted or wrong-purpose flow")
    row = await db.get(AuthCode, flow_id, populate_existing=True)
    if row is None or not hmac.compare_digest(row.code_hash, _digest(flow_id, code)):
        raise AuthFailedError("wrong code")
    consumed = await db.execute(
        update(AuthCode)
        .where(*open_flow)
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if consumed.rowcount != 1:  # type: ignore[attr-defined]
        raise AuthFailedError("flow consumed concurrently")
    return row


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


# --- sign-up ----------------------------------------------------------------------


async def start_signup(db: AsyncSession, deps: Deps, form: SignUpForm) -> uuid.UUID:
    check_password_policy(form.password, form.email)
    # Hash even when the email is taken so both branches cost the same.
    password_hash = await hash_password(form.password)
    if await _user_by_email(db, form.email) is not None:
        await _send(deps, email=form.email, locale=form.locale, template="account_exists")
        return await _issue(
            db, deps, purpose="signup", email=form.email, locale=form.locale, template=None
        )
    return await _issue(
        db,
        deps,
        purpose="signup",
        email=form.email,
        locale=form.locale,
        payload={
            "display_name": form.display_name,
            "locale": form.locale,
            "password_hash": password_hash,
        },
        template="signup_code",
    )


async def finish_signup(db: AsyncSession, flow_id: uuid.UUID, code: str) -> User:
    flow = await _check(db, flow_id, "signup", code)
    payload = flow.payload
    if "password_hash" not in payload or await _user_by_email(db, flow.email) is not None:
        raise AuthFailedError("email already registered")
    now = utcnow()
    user = User(
        handle=f"u_{secrets.token_hex(8)}",
        display_name=str(payload["display_name"]),
        locale=str(payload["locale"]),
        email=flow.email,
        email_verified_at=now,
        password_hash=str(payload["password_hash"]),
        # Both declarations were required (Literal[True]) to start this flow.
        age_confirmed_at=now,
        ai_disclosure_accepted_at=now,
    )
    db.add(user)
    await db.commit()
    return user


# --- sign-in ----------------------------------------------------------------------


async def start_login(db: AsyncSession, deps: Deps, email: str, password: str) -> uuid.UUID:
    user = await _user_by_email(db, email)
    stored = user.password_hash if user is not None and user.password_hash else None
    valid = await _verify_password(stored or await _dummy(), password)
    if user is None or stored is None or not valid:
        raise AuthFailedError("unknown email or wrong password")
    if _hasher.check_needs_rehash(stored):
        user.password_hash = await hash_password(password)
        await db.commit()
    return await _issue(
        db,
        deps,
        purpose="login",
        email=email,
        locale=user.locale,
        user_id=user.id,
        template="login_code",
    )


async def finish_login(db: AsyncSession, flow_id: uuid.UUID, code: str) -> User:
    flow = await _check(db, flow_id, "login", code)
    user = await db.get(User, flow.user_id) if flow.user_id else None
    if user is None:
        raise AuthFailedError("user vanished")
    return user


# --- password reset ---------------------------------------------------------------


async def start_reset(db: AsyncSession, deps: Deps, email: str, locale: str) -> uuid.UUID:
    user = await _user_by_email(db, email)
    if user is None:
        return await _issue(db, deps, purpose="reset", email=email, locale=locale, template=None)
    return await _issue(
        db,
        deps,
        purpose="reset",
        email=email,
        locale=user.locale,
        user_id=user.id,
        template="password_reset_code",
    )


async def finish_reset(
    db: AsyncSession, deps: Deps, flow_id: uuid.UUID, code: str, new_password: str
) -> None:
    row = await db.get(AuthCode, flow_id)
    if row is not None:
        # Policy first, so a weak password does not burn the code.
        check_password_policy(new_password, row.email)
    flow = await _check(db, flow_id, "reset", code)
    user = await db.get(User, flow.user_id) if flow.user_id else None
    if user is None:
        raise AuthFailedError("user vanished")
    user.password_hash = await hash_password(new_password)
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    await _send(
        deps, email=flow.email, locale=user.locale, template="password_changed", limited=False
    )
