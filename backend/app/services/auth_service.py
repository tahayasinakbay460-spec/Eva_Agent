"""Passkey sign-up and sign-in (CLAUDE.md §11.2, ADR 0002, docs/threat-model.md §1).

Every WebAuthn ceremony is two calls:

1. ``begin_*`` stores a random single-use challenge and returns browser options.
2. ``finish_*`` atomically consumes the challenge, then lets py_webauthn verify the
   browser's response (origin, RP ID, signature, user verification, sign counter).

Every failure raises the same ``AuthFailedError`` so callers cannot tell which check
failed (no account or credential enumeration).
"""

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import parse_authentication_credential_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import Settings
from app.database import utcnow
from app.models.auth import AuthChallenge, Passkey
from app.models.user import User

PURPOSE_REGISTER = "register"
PURPOSE_LOGIN = "login"


class AuthFailedError(Exception):
    """Generic authentication failure. The message is for tests, never for clients."""


@dataclass(frozen=True, slots=True)
class CeremonyOptions:
    flow_id: uuid.UUID
    options: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SignUpForm:
    display_name: str
    locale: str


# --- helpers ----------------------------------------------------------------------


async def _new_challenge(
    db: AsyncSession,
    settings: Settings,
    *,
    purpose: str,
    challenge: bytes,
    payload: dict[str, Any] | None = None,
) -> uuid.UUID:
    now = utcnow()
    # Opportunistic cleanup keeps the table small without a scheduled job.
    await db.execute(delete(AuthChallenge).where(AuthChallenge.expires_at < now))
    row = AuthChallenge(
        purpose=purpose,
        challenge=challenge,
        payload=payload or {},
        expires_at=now + timedelta(seconds=settings.auth_challenge_ttl_s),
    )
    db.add(row)
    await db.commit()
    return row.id


async def _consume_challenge(db: AsyncSession, flow_id: uuid.UUID, purpose: str) -> AuthChallenge:
    """Mark the flow used, atomically. A second call with the same flow fails."""
    now = utcnow()
    result = await db.execute(
        update(AuthChallenge)
        .where(
            AuthChallenge.id == flow_id,
            AuthChallenge.purpose == purpose,
            AuthChallenge.consumed_at.is_(None),
            AuthChallenge.expires_at > now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise AuthFailedError("unknown, expired, reused or wrong-purpose flow")
    row = await db.get(AuthChallenge, flow_id)
    if row is None:  # pragma: no cover - just updated
        raise AuthFailedError("flow vanished")
    return row


def _options_dict(options: object) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(options_to_json(options))  # type: ignore[arg-type]
    return parsed


# --- sign-up ----------------------------------------------------------------------


async def begin_registration(
    db: AsyncSession, settings: Settings, form: SignUpForm
) -> CeremonyOptions:
    """Start sign-up. Nothing is written to ``users`` until the passkey is verified."""
    webauthn_user_id = secrets.token_bytes(32)
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_name=form.display_name,
        user_id=webauthn_user_id,
        user_display_name=form.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    flow_id = await _new_challenge(
        db,
        settings,
        purpose=PURPOSE_REGISTER,
        challenge=options.challenge,
        payload={
            "display_name": form.display_name,
            "locale": form.locale,
            "webauthn_user_id": webauthn_user_id.hex(),
        },
    )
    return CeremonyOptions(flow_id, _options_dict(options))


async def finish_registration(
    db: AsyncSession, settings: Settings, flow_id: uuid.UUID, credential: dict[str, Any]
) -> User:
    flow = await _consume_challenge(db, flow_id, PURPOSE_REGISTER)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=flow.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origins,
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        raise AuthFailedError(f"registration rejected: {type(exc).__name__}") from exc

    existing = await db.execute(
        select(Passkey.id).where(Passkey.credential_id == verified.credential_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise AuthFailedError("credential already registered")

    now = utcnow()
    payload = flow.payload
    user = User(
        handle=f"u_{secrets.token_hex(8)}",
        display_name=str(payload["display_name"]),
        locale=str(payload["locale"]),
        webauthn_user_id=bytes.fromhex(str(payload["webauthn_user_id"])),
        # Both declarations were required (Literal[True]) to start this flow.
        age_confirmed_at=now,
        ai_disclosure_accepted_at=now,
    )
    db.add(user)
    await db.flush()
    transports = credential.get("response", {}).get("transports") or []
    db.add(
        Passkey(
            user_id=user.id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=[str(t) for t in transports if isinstance(t, str)][:8],
            aaguid=verified.aaguid,
            backed_up=verified.credential_backed_up,
            last_used_at=now,
        )
    )
    await db.commit()
    return user


# --- sign-in ----------------------------------------------------------------------


async def begin_login(db: AsyncSession, settings: Settings) -> CeremonyOptions:
    """Discoverable-credential login: no username is asked, so none can be enumerated."""
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    flow_id = await _new_challenge(db, settings, purpose=PURPOSE_LOGIN, challenge=options.challenge)
    return CeremonyOptions(flow_id, _options_dict(options))


async def finish_login(
    db: AsyncSession, settings: Settings, flow_id: uuid.UUID, credential: dict[str, Any]
) -> User:
    flow = await _consume_challenge(db, flow_id, PURPOSE_LOGIN)
    try:
        parsed = parse_authentication_credential_json(credential)
    except WebAuthnException as exc:
        raise AuthFailedError("malformed credential") from exc

    result = await db.execute(select(Passkey).where(Passkey.credential_id == parsed.raw_id))
    passkey = result.scalar_one_or_none()
    if passkey is None:
        raise AuthFailedError("unknown credential")
    user = await db.get(User, passkey.user_id)
    if user is None:  # pragma: no cover - FK cascade
        raise AuthFailedError("credential without user")
    if parsed.response.user_handle is not None and parsed.response.user_handle != (
        user.webauthn_user_id
    ):
        raise AuthFailedError("user handle mismatch")

    try:
        verified = verify_authentication_response(
            credential=parsed,
            expected_challenge=flow.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origins,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        raise AuthFailedError(f"assertion rejected: {type(exc).__name__}") from exc

    passkey.sign_count = verified.new_sign_count
    passkey.backed_up = verified.credential_backed_up
    passkey.last_used_at = utcnow()
    await db.commit()
    return user
