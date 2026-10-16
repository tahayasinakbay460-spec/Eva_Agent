"""Şifreli dosya deposu (§11.3, §11.4): diskte düz veri yok, anahtarlar kullanıcıya bağlı."""

import uuid
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from fastapi import FastAPI
from sqlalchemy import select

from app.models.storage import UserDataKey
from app.models.user import User
from app.storage.blobs import LocalBlobStore
from app.storage.encrypted import EncryptedStore
from app.storage.factory import StorageConfigError, build_encrypted_store, check_storage
from app.storage.keys import LocalKeyWrapper, load_or_create_dev_master_key
from tests.conftest import make_settings

SECRET = b"RIFF....WAVE ham ses ornegi"


async def _user(app: FastAPI, handle: str) -> uuid.UUID:
    async with app.state.session_factory() as db:
        user = User(handle=handle, display_name=handle)
        db.add(user)
        await db.commit()
        return user.id


def _files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


async def test_round_trip_and_nothing_plain_on_disk(app: FastAPI, tmp_path: Path) -> None:
    store: EncryptedStore = app.state.store
    user_id = await _user(app, "ayse")
    async with app.state.session_factory() as db:
        await store.put(db, user_id, "biometric", f"{user_id}/a", SECRET)
        await db.commit()
        assert await store.get(db, user_id, "biometric", f"{user_id}/a") == SECRET

    files = _files(tmp_path / "storage")
    assert len(files) == 1
    assert files[0].parent.parent.name == "biometric", "biometric bucket is separate"
    assert SECRET not in files[0].read_bytes()


async def test_data_key_is_stored_wrapped(app: FastAPI) -> None:
    store: EncryptedStore = app.state.store
    user_id = await _user(app, "ayse")
    async with app.state.session_factory() as db:
        await store.put(db, user_id, "biometric", f"{user_id}/a", SECRET)
        await db.commit()
        row = (await db.execute(select(UserDataKey))).scalar_one()
        assert row.kek_id == "local-v1"
        assert len(row.wrapped_key) == 12 + 32 + 16, "nonce + key + tag, never the plain key"


async def test_swapped_files_do_not_decrypt(app: FastAPI, tmp_path: Path) -> None:
    """Bir dosyayı başka bir kaydın yerine koymak işe yaramaz (yer, şifreye bağlı)."""
    store: EncryptedStore = app.state.store
    user_id = await _user(app, "ayse")
    async with app.state.session_factory() as db:
        await store.put(db, user_id, "biometric", f"{user_id}/a", b"a")
        await store.put(db, user_id, "biometric", f"{user_id}/b", b"b")
        await db.commit()
        base = tmp_path / "storage" / "biometric" / str(user_id)
        (base / "b").write_bytes((base / "a").read_bytes())
        with pytest.raises(InvalidTag):
            await store.get(db, user_id, "biometric", f"{user_id}/b")


async def test_wrapped_key_is_bound_to_its_user(app: FastAPI) -> None:
    store: EncryptedStore = app.state.store
    alice, bob = await _user(app, "alice"), await _user(app, "bob")
    async with app.state.session_factory() as db:
        await store.put(db, alice, "biometric", f"{alice}/a", b"a")
        await store.put(db, bob, "biometric", f"{bob}/a", b"b")
        await db.commit()
        rows = {r.user_id: r for r in (await db.execute(select(UserDataKey))).scalars()}
        rows[bob].wrapped_key = rows[alice].wrapped_key
        await db.commit()
        with pytest.raises(InvalidTag):
            await store.get(db, bob, "biometric", f"{bob}/a")


async def test_crypto_shred_makes_files_unreadable(app: FastAPI) -> None:
    store: EncryptedStore = app.state.store
    user_id = await _user(app, "ayse")
    async with app.state.session_factory() as db:
        await store.put(db, user_id, "biometric", f"{user_id}/a", SECRET)
        await db.commit()
        await EncryptedStore.crypto_shred(db, user_id)
        await db.commit()
        with pytest.raises(LookupError):
            await store.get(db, user_id, "biometric", f"{user_id}/a")


async def test_delete_is_idempotent(app: FastAPI) -> None:
    store: EncryptedStore = app.state.store
    await store.delete("biometric", "nothing-here")


@pytest.mark.parametrize("key", ["../x", "a/../../x", "/abs", "A", "a//b", "a\\b", ""])
async def test_blob_keys_cannot_escape_the_root(tmp_path: Path, key: str) -> None:
    blobs = LocalBlobStore(tmp_path)
    with pytest.raises(ValueError, match="invalid blob key"):
        await blobs.put("media", key, b"x")


def test_master_key_file_is_reused(tmp_path: Path) -> None:
    path = tmp_path / "mk"
    assert load_or_create_dev_master_key(path) == load_or_create_dev_master_key(path)


def test_wrapper_rejects_wrong_size_key() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        LocalKeyWrapper(b"short")


def test_local_master_key_is_refused_outside_dev(tmp_path: Path) -> None:
    store = build_encrypted_store(make_settings(tmp_path, env="prod"))
    with pytest.raises(StorageConfigError):
        check_storage(store)
