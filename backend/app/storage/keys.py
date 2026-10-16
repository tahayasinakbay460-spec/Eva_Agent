"""Zarf şifreleme (envelope encryption) için anahtar sarmalayıcıları (§11.4).

Mantık iki katmanlı:
- Her kullanıcının kendi **veri anahtarı** (DEK) var; dosyaları bu anahtar şifreler.
- Veri anahtarları veritabanında **ana anahtarla** (KEK) şifrelenmiş ("sarmalanmış") durur.
  Ana anahtar veritabanında değil; prod'da KMS'te, geliştirmede yerel bir dosyada.

Veritabanı tek başına sızarsa dosyalar okunamaz. Kullanıcının veri anahtarı silinirse
o kullanıcının tüm dosyaları kalıcı olarak okunamaz olur ("kripto-silme").
"""

import base64
import os
import secrets
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12
_BLOB_MAGIC = b"EVA1"


class KeyWrapper(Protocol):
    """Veri anahtarlarını ana anahtarla sarar/açar. KMS adaptörü de bu arayüzü uygular."""

    key_id: str

    def wrap(self, data_key: bytes, *, context: bytes) -> bytes: ...

    def unwrap(self, wrapped: bytes, *, context: bytes) -> bytes: ...


class LocalKeyWrapper:
    """Ana anahtarı süreç belleğinde tutan sarmalayıcı (yalnızca dev/test).

    ``context`` (kullanıcı id'si) ek doğrulanan veri (AAD) olarak bağlanır: bir
    kullanıcının sarmalanmış anahtarı başka bir kullanıcının satırına kopyalanırsa açılmaz.
    """

    def __init__(self, master_key: bytes, key_id: str = "local-v1") -> None:
        if len(master_key) != KEY_BYTES:
            raise ValueError("master key must be 32 bytes")
        self._aead = AESGCM(master_key)
        self.key_id = key_id

    def wrap(self, data_key: bytes, *, context: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, data_key, context)

    def unwrap(self, wrapped: bytes, *, context: bytes) -> bytes:
        nonce, sealed = wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:]
        return self._aead.decrypt(nonce, sealed, context)


def load_or_create_dev_master_key(path: Path) -> bytes:
    """Geliştirme için ana anahtarı yerel bir dosyadan okur, yoksa oluşturur.

    Bu dosya git'e girmez (.gitignore). Silinirse şifreli dev dosyaları okunamaz olur;
    geliştirmede bu kabul edilebilir.
    """
    if path.exists():
        return base64.b64decode(path.read_text(encoding="ascii").strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(KEY_BYTES)
    path.write_text(base64.b64encode(key).decode("ascii"), encoding="ascii")
    return key


def new_data_key() -> bytes:
    return secrets.token_bytes(KEY_BYTES)


def seal(data_key: bytes, plaintext: bytes, *, aad: bytes) -> bytes:
    """AES-256-GCM ile şifreler. ``aad`` (dosyanın yeri) şifreye bağlanır: şifreli dosya
    başka bir kaydın yerine konursa açılmaz."""
    nonce = os.urandom(NONCE_BYTES)
    return _BLOB_MAGIC + nonce + AESGCM(data_key).encrypt(nonce, plaintext, aad)


def open_sealed(data_key: bytes, blob: bytes, *, aad: bytes) -> bytes:
    if blob[: len(_BLOB_MAGIC)] != _BLOB_MAGIC:
        raise ValueError("unknown blob format")
    start = len(_BLOB_MAGIC)
    nonce, sealed = blob[start : start + NONCE_BYTES], blob[start + NONCE_BYTES :]
    return AESGCM(data_key).decrypt(nonce, sealed, aad)
