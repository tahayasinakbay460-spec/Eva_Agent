# EVA threat model (STRIDE)

Required by CLAUDE.md §11.1 for authentication, Legacy (Miras), biometric enrollment
and persona prompts. Updated **before** each security-critical feature ships.

## 1. Authentication (passkey + MFA) — 2026-10-16

Assets: user accounts and everything behind them (memories, voice/face, Legacy keys).
Trust boundary: browser/app ↔ API. Decision: [ADR 0002](adr/0002-authentication.md).

| STRIDE | Threat | Mitigation | Test |
|---|---|---|---|
| Spoofing | Phishing site relays a passkey ceremony | WebAuthn origin + RP ID checked by py_webauthn; only configured origins accepted | wrong origin / wrong RP ID rejected |
| Spoofing | Replay of a captured assertion | Server-stored single-use challenge, 5 min TTL, consumed before verification result is used | reused flow_id rejected; expired flow rejected |
| Spoofing | Cloned authenticator | Signature counter must increase when non-zero (py_webauthn) | — (library) |
| Spoofing | Passkey without user verification (stolen unlocked key) | `user_verification=required` on both ceremonies | UV flag missing → rejected |
| Tampering | Client edits challenge purpose (login flow used to register) | Flow row stores its purpose; verify endpoint checks it | login flow on register endpoint rejected |
| Repudiation | User denies a login | Audit log of auth events (Phase 5 `audit_log`); for now session rows keep created_at | — |
| Information disclosure | Account enumeration via error messages | One generic error for every verification failure; discoverable login needs no username | same error body for all failures |
| Information disclosure | DB leak exposes sessions | Only SHA-256 digests of tokens stored; credential public keys are not secret | existing |
| Information disclosure | Logs leak credentials | Credentials, challenges and tokens are never logged (§2.6) | — (review) |
| Denial of service | Challenge table flooding / brute force | Per-IP auth rate limit on every endpoint; expired flows pruned | rate limit test |
| Elevation of privilege | Under-18 sign-up (§12) | Age declaration required at sign-up; risk-based verification later | sign-up without declaration rejected |
| Elevation of privilege | dev-login reachable in prod | Endpoint returns 404 unless `EVA_ENV` is dev/test | existing |

Open items (next steps): TOTP second factor + recovery codes, short-lived access token
with refresh rotation and reuse detection, step-up for sensitive actions, device/session
list, new-device notification.
