"""Kullanıcı başına veri anahtarıyla şifreli dosya saklama (§11.3, §11.4)."""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage import UserDataKey
from app.storage.blobs import BlobStore, Bucket
from app.storage.keys import KeyWrapper, new_data_key, open_sealed, seal


class EncryptedStore:
    def __init__(self, blobs: BlobStore, wrapper: KeyWrapper) -> None:
        self._blobs = blobs
        self._wrapper = wrapper

    @property
    def key_wrapper(self) -> KeyWrapper:
        return self._wrapper

    async def _data_key(self, db: AsyncSession, user_id: uuid.UUID, *, create: bool) -> bytes:
        context = user_id.bytes
        row = await db.get(UserDataKey, user_id)
        if row is None:
            if not create:
                raise LookupError("user has no data key")
            key = new_data_key()
            db.add(
                UserDataKey(
                    user_id=user_id,
                    wrapped_key=self._wrapper.wrap(key, context=context),
                    kek_id=self._wrapper.key_id,
                )
            )
            await db.flush()
            return key
        return self._wrapper.unwrap(row.wrapped_key, context=context)

    async def put(
        self, db: AsyncSession, user_id: uuid.UUID, bucket: Bucket, key: str, data: bytes
    ) -> None:
        """Dosyayı şifreleyip yazar. Veri anahtarı yeni oluştuysa commit çağıranın işi."""
        data_key = await self._data_key(db, user_id, create=True)
        await self._blobs.put(bucket, key, seal(data_key, data, aad=_aad(bucket, key)))

    async def get(self, db: AsyncSession, user_id: uuid.UUID, bucket: Bucket, key: str) -> bytes:
        data_key = await self._data_key(db, user_id, create=False)
        return open_sealed(data_key, await self._blobs.get(bucket, key), aad=_aad(bucket, key))

    async def delete(self, bucket: Bucket, key: str) -> None:
        await self._blobs.delete(bucket, key)

    @staticmethod
    async def crypto_shred(db: AsyncSession, user_id: uuid.UUID) -> None:
        """Kullanıcının veri anahtarını siler: kalan tüm şifreli dosyaları (yedekler dahil)
        kalıcı olarak okunamaz olur. Commit çağıranın işi."""
        await db.execute(delete(UserDataKey).where(UserDataKey.user_id == user_id))


def _aad(bucket: Bucket, key: str) -> bytes:
    return f"{bucket}/{key}".encode()
