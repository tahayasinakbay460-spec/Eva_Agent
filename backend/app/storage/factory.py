"""Ayarlara göre şifreli depoyu kurar (API ve işçi aynı yerden)."""

from app.core.config import Settings
from app.storage.blobs import LocalBlobStore
from app.storage.encrypted import EncryptedStore
from app.storage.keys import LocalKeyWrapper, load_or_create_dev_master_key


class StorageConfigError(RuntimeError):
    pass


class MissingKeyWrapper:
    """Gerçek ortamda KMS bağlanana kadar yer tutucu: her kullanımda hata verir. Uygulama
    zaten açılışta durdurulur (``check_storage``); bu sadece ikinci emniyet kemeri."""

    key_id = "missing"

    def wrap(self, data_key: bytes, *, context: bytes) -> bytes:
        raise StorageConfigError("a KMS key wrapper is required outside dev/test")

    def unwrap(self, wrapped: bytes, *, context: bytes) -> bytes:
        raise StorageConfigError("a KMS key wrapper is required outside dev/test")


def build_encrypted_store(settings: Settings) -> EncryptedStore:
    if not settings.is_dev:
        # Yerel dosyadaki ana anahtar yalnızca geliştirme içindir. Gerçek ortamda ana
        # anahtar KMS'te durmalı; KMS adaptörü barındırma kararıyla (§15) birlikte gelecek.
        return EncryptedStore(LocalBlobStore(settings.storage_dir), MissingKeyWrapper())
    master_key = load_or_create_dev_master_key(settings.dev_master_key_file)
    return EncryptedStore(LocalBlobStore(settings.storage_dir), LocalKeyWrapper(master_key))


def check_storage(store: EncryptedStore) -> None:
    """Uygulama açılırken çağrılır: ana anahtar yoksa hiç açılmasın."""
    if isinstance(store.key_wrapper, MissingKeyWrapper):
        raise StorageConfigError("a KMS key wrapper is required outside dev/test")
