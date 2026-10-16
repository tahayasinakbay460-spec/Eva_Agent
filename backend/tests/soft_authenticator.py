"""Testler için yazılımla taklit edilmiş bir WebAuthn (passkey) doğrulayıcısı.

Gerçek bir tarayıcı + cihaz doğrulayıcısının (ör. telefondaki parmak izi) göndereceği
baytları birebir üretir (``none`` attestation, ES256 anahtarlar). Böylece sunucudaki
gerçek py_webauthn doğrulaması baştan sona çalışır. Ayar düğmeleri sayesinde testler,
tehdit modelinde sayılan hataları (ör. doğrulanmamış kullanıcı) bilerek üretebilir.
"""

import base64
import hashlib
import json
import secrets
import struct
from dataclasses import dataclass, field
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_UP = 0x01  # kullanıcı cihazın başında (dokundu)
FLAG_UV = 0x04  # kullanıcı doğrulandı (biyometrik / PIN)
FLAG_AT = 0x40  # yeni anahtar bilgisi (attested credential data) ekte


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


@dataclass
class SoftAuthenticator:
    origin: str = "http://localhost:3000"
    rp_id: str = "localhost"
    user_verified: bool = True
    credential_id: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    sign_count: int = 0
    user_handle: bytes | None = None

    def _flags(self, extra: int = 0) -> bytes:
        return bytes([FLAG_UP | (FLAG_UV if self.user_verified else 0) | extra])

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False},
            separators=(",", ":"),
        ).encode()

    def _cose_public_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def create(self, options: dict[str, Any]) -> dict[str, Any]:
        """Tarayıcıdaki ``navigator.credentials.create(options)`` çağrısının cevabını üretir."""
        self.user_handle = b64url_decode(options["user"]["id"])
        client_data = self._client_data("webauthn.create", options["challenge"])
        attested = (
            bytes(16)  # AAGUID (tamamen sıfır; "none" kullanan çoğu cihaz da böyle gönderir)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_public_key()
        )
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + self._flags(FLAG_AT)
            + struct.pack(">I", self.sign_count)
            + attested
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options: dict[str, Any], *, advance_counter: bool = True) -> dict[str, Any]:
        """Tarayıcıdaki ``navigator.credentials.get(options)`` çağrısının cevabını üretir."""
        if advance_counter:
            self.sign_count += 1
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + self._flags()
            + struct.pack(">I", self.sign_count)
        )
        signed = auth_data + hashlib.sha256(client_data).digest()
        signature = self.key.sign(signed, ec.ECDSA(hashes.SHA256()))
        response: dict[str, Any] = {
            "clientDataJSON": b64url(client_data),
            "authenticatorData": b64url(auth_data),
            "signature": b64url(signature),
        }
        if self.user_handle is not None:
            response["userHandle"] = b64url(self.user_handle)
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": response,
            "clientExtensionResults": {},
        }
