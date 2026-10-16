# ADR 0002: Authentication is built in-house on py_webauthn and pyotp

Date: 2026-10-16 · Status: accepted (owner chose option A)

## Context

CLAUDE.md §11.2 requires passkey (WebAuthn) + MFA, short-lived access tokens, refresh
token rotation with reuse detection, step-up authentication and device/session
management. §15 left the solution open, preferring something self-hostable. §2.10
forbids home-made cryptography.

Options considered:

- **A. In-house, on mature libraries:** `webauthn` (py_webauthn, Duo Labs) for passkey
  ceremonies, `pyotp` for TOTP. Runs inside the existing FastAPI app.
- **B. Separate identity server** (Keycloak, Ory Kratos): more features out of the box,
  but a second service to run and secure, and Docker is not available locally yet.

## Decision

Option A. The libraries do all cryptographic verification; our code only stores
credentials, issues challenges and manages sessions.

- **Passkeys are discoverable and require user verification** (biometric or device
  PIN). A UV passkey is already two factors (possession + inherence/knowledge) and is
  phishing-resistant, so it satisfies "MFA" on its own (NIST SP 800-63B AAL2+).
- **TOTP** is added as a second factor for recovery and for accounts without a
  passkey on the current device (next step, not in the first passkey PR).
- Challenges are single-use, server-stored, 5-minute TTL.
- Sessions keep the existing opaque-token model (only SHA-256 digests stored).
  Refresh rotation and step-up follow in later steps.

## Consequences

- No extra service to deploy; auth lives in `backend/app/routers/auth.py` and
  `backend/app/services/auth_service.py`.
- WebAuthn binds credentials to the relying-party ID (domain). Changing the production
  domain later invalidates passkeys, so `EVA_WEBAUTHN_RP_ID` must be chosen once.
- Swapping to an identity server later is possible: sessions and `get_current_user`
  are the only touchpoints for the rest of the app.

## Amendment (2026-10-16): email + password, confirmed by an emailed code

The owner asked for a password option next to passkeys for user experience. Because a
password is a single factor, every password sign-in also requires a 6-digit code sent
to the verified email address (owner's choice over an authenticator app; replaceable
later with TOTP or SMS without changing the flow shape: the API answers
`{flow_id, method}` and the client asks for a code).

- Email is the login name, stored lower-case; the account is created only after the
  emailed code is entered.
- Passwords: 10–128 characters, Argon2id via `argon2-cffi`.
- Until an email provider is chosen (§15), dev emails are written to
  `backend/dev_mailbox/`; the app refuses to start in staging/prod with that adapter.
- Threats and mitigations: docs/threat-model.md §2. Residual risk: whoever controls the
  email account can reset the password; the UI recommends passkeys.
