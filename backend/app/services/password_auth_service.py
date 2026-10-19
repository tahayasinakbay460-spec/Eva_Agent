"""E-posta + şifre ile kayıt, giriş ve şifre sıfırlama; her biri e-postayla gelen kodla onaylanır.

Bkz. docs/threat-model.md §2. Her akışın şekli aynıdır:

1. ``start_*`` kontrol edebildiğini kontrol eder, yeni bir akış id'sine bağlı 6 haneli
   kodun özetini (hash) saklar, kodu e-postayla gönderir ve akış id'sini döndürür.
2. ``finish_*`` kodu kontrol eder (deneme sayısı sınırlı, tek kullanımlık) ve akışı bitirir.

Kayıt ve sıfırlama, e-postanın hesabı olsa da olmasa da aynı cevabı verir; giriş de
"bilinmeyen e-posta" ve "yanlış şifre" için tek bir hata verir (üstelik aynı sürede).
Böylece hiçbiri kimin kayıtlı olduğunu ele vermez. Her hata ``AuthFailedError`` fırlatır.
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

Purpose = Literal["signup", "login", "reset", "step_up", "legacy", "legacy_delete"]

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
# Birinin e-postasını kodlarla doldurmayı (mail bombing) önleyen, adres başına gönderim
# sınırı (IP başına istek sınırına ek olarak).
MAIL_LIMIT = 5
MAIL_WINDOW_S = 600.0

_hasher = PasswordHasher()  # Argon2id, RFC 9106 parametreleri (argon2-cffi varsayılanları)
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
    """Şifre kurallara uymuyor; bunu kullanıcıya söylemek güvenli (hesaplar hakkında bilgi
    vermez)."""


# --- şifre özetleme (hash) ---------------------------------------------------------


def check_password_policy(password: str, email: str) -> None:
    if not 10 <= len(password) <= 128:
        raise WeakPasswordError("length")
    if password.strip().casefold() == email.casefold():
        raise WeakPasswordError("equals_email")


async def hash_password(password: str) -> str:
    # Argon2 bilerek yavaştır (~50 ms, 64 MiB); event loop'u kilitlemesin diye ayrı
    # bir thread'de çalıştırılır.
    return await asyncio.to_thread(_hasher.hash, password)


async def _verify_password(stored_hash: str, password: str) -> bool:
    def verify() -> bool:
        try:
            return _hasher.verify(stored_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    return await asyncio.to_thread(verify)


async def _dummy() -> str:
    """E-posta bilinmiyorsa karşılaştırma için gerçek bir Argon2 özeti (cevap süresi aynı
    kalsın, süreden hesabın var olup olmadığı anlaşılmasın)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = await hash_password(secrets.token_urlsafe(16))
    return _dummy_hash


# --- kodlar -----------------------------------------------------------------------


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
    """Yeni bir kod saklar (aynı e-posta+amaç için açık eski kodlar geçersiz olur) ve gönderir.

    ``template=None`` asla başarılı olamayacak sahte (yem) bir akış oluşturur (bilinmeyen
    e-posta için; dışarıdan gerçek akıştan ayırt edilemez).
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
            # Sahte akışlar, kimseye gönderilmemiş rastgele bir şeyin özetini saklar.
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
    # Giriş yapmamış birinin tetikleyebildiği her gönderim adres başına sınırlanır; önce
    # geçerli kod gerektiren bildirimler (şifre değişti) sınırlanmaz, gerçek kodların
    # önünü tıkamasınlar.
    if limited and not await deps.limiter.hit(f"mail:{email}", MAIL_LIMIT, MAIL_WINDOW_S):
        return  # sessizce atlanır: cevap farklı olmamalı
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
    # Önce denemeyi tek adımda (atomik) say; böylece aynı anda yapılan tahminler sınırı aşamaz.
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


# --- kayıt ------------------------------------------------------------------------


async def start_signup(db: AsyncSession, deps: Deps, form: SignUpForm) -> uuid.UUID:
    check_password_policy(form.password, form.email)
    # E-posta alınmış olsa bile hash'le; iki dal da aynı sürede bitsin.
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
        # Bu akışı başlatmak için iki beyan da zorunluydu (Literal[True]).
        age_confirmed_at=now,
        ai_disclosure_accepted_at=now,
    )
    db.add(user)
    await db.commit()
    return user


# --- giriş ------------------------------------------------------------------------


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


# --- şifre sıfırlama --------------------------------------------------------------


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
        # Önce şifre kuralları; zayıf şifre yüzünden kod boşa harcanmasın.
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


# --- adım-yukarı doğrulama (§11.2) ------------------------------------------------


async def start_step_up(db: AsyncSession, deps: Deps, user: User, password: str) -> uuid.UUID:
    """Giriş yapmış kullanıcının şifresini yeniden sorar, sonra e-postasına kod gönderir
    (yani hassas işlem için yine iki kilit: şifre + e-posta)."""
    if user.email is None or user.password_hash is None:
        raise AuthFailedError("user has no password")
    if not await _verify_password(user.password_hash, password):
        raise AuthFailedError("wrong password")
    return await _issue(
        db,
        deps,
        purpose="step_up",
        email=user.email,
        locale=user.locale,
        user_id=user.id,
        template="step_up_code",
    )


async def finish_step_up(db: AsyncSession, user: User, flow_id: uuid.UUID, code: str) -> None:
    row = await db.get(AuthCode, flow_id)
    # Başkasının akışına kod denemek, o akışın deneme hakkını bile harcamasın.
    if row is None or row.user_id != user.id:
        raise AuthFailedError("flow belongs to another user")
    await _check(db, flow_id, "step_up", code)


# Miras anahtarını kullanırken (§8.3) aynı kod altyapısı kullanılır.
issue_code = _issue
check_code = _check
send_message = _send
