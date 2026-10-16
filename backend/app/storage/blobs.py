"""Ham dosya deposu (şifreleme bunun üstünde, ``EncryptedStore``'da yapılır).

Lokalde dosya sistemi; prod'da S3 uyumlu bir depo aynı arayüzle eklenecek (§3).
Biyometrik örnekler ayrı bir "kova"dadır (bucket), diğer medyayla karışmaz (§11.3).
"""

import asyncio
import re
from pathlib import Path
from typing import Literal, Protocol

Bucket = Literal["biometric", "media"]

# Anahtarlar her zaman sunucuda üretilir (uuid'lerden); kullanıcı girdisi asla yol olmaz.
# Yine de klasör dışına çıkmayı (../) imkânsız kılmak için biçimi kontrol ediyoruz.
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9/_-]{0,200}$")


class BlobStore(Protocol):
    async def put(self, bucket: Bucket, key: str, data: bytes) -> None: ...

    async def get(self, bucket: Bucket, key: str) -> bytes: ...

    async def delete(self, bucket: Bucket, key: str) -> None:
        """İdempotent: olmayan dosyayı silmek hata değildir."""
        ...


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, bucket: Bucket, key: str) -> Path:
        if not _KEY_RE.match(key) or ".." in key or "//" in key:
            raise ValueError("invalid blob key")
        return self._root / bucket / key

    async def put(self, bucket: Bucket, key: str, data: bytes) -> None:
        path = self._path(bucket, key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)  # yarım yazılmış dosya asla gerçek adıyla görünmesin

        await asyncio.to_thread(write)

    async def get(self, bucket: Bucket, key: str) -> bytes:
        return await asyncio.to_thread(self._path(bucket, key).read_bytes)

    async def delete(self, bucket: Bucket, key: str) -> None:
        await asyncio.to_thread(self._path(bucket, key).unlink, missing_ok=True)
