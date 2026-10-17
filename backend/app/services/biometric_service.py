"""Rızalı ses/yüz kaydı (CLAUDE.md §11.3; Faz 3). Tehdit modeli: docs/threat-model.md §5.

Akış: başlat (adım-yukarı) → örnekleri ve rıza videosunu yükle → gönder (adım-yukarı; rıza
kaydı yazılır) → inceleme bekliyor → admin onaylar → işçi sağlayıcıda klonu oluşturur → aktif.
Geri alma (adım-yukarı): kullanım anında durur; işçi klonu sağlayıcıdan siler ve dosyaları
imha eder. Onaysız hiçbir klon oluşturulmaz (sahibin kararı: her kayıt elle incelenir).
"""

import asyncio
import hashlib
import io
import secrets
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database import utcnow
from app.models.biometric import (
    OPEN_STATUSES,
    BiometricEnrollment,
    Consent,
    ConsentRecord,
    EnrollmentSample,
    ProviderAsset,
)
from app.models.user import User
from app.providers.base import AudioFormat, TTSRequest
from app.providers.registry import ProviderKind, ProviderRegistry
from app.services import audit, consent_texts
from app.storage.encrypted import EncryptedStore
from app.worker import queue
from app.worker.jobs import BIOMETRIC_CREATE_ASSET, BIOMETRIC_PURGE

Kind = Literal["voice", "face"]
FileRole = Literal["sample", "consent_recording"]
RejectReason = Literal[
    "not_adult", "different_person", "code_mismatch", "poor_quality", "not_consenting", "other"
]

MAX_SAMPLES = 5
MB = 1024 * 1024
SIZE_LIMITS: dict[tuple[Kind, FileRole], int] = {
    ("voice", "sample"): 15 * MB,
    ("face", "sample"): 80 * MB,
    ("voice", "consent_recording"): 40 * MB,
    ("face", "consent_recording"): 40 * MB,
}
AUDIO_TYPES = frozenset({"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/mpeg"})
VIDEO_TYPES = frozenset({"video/webm", "video/mp4"})
# Yüz fotoğrafı: tek fotoğraftan avatar üreten sağlayıcılar (ör. LemonSlice) için.
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
IMAGE_SIZE_LIMIT = 10 * MB
# Çok büyük çözünürlüklü "sıkıştırma bombası" görsellere karşı (açınca belleği doldurur).
IMAGE_MAX_PIXELS = 40_000_000
# Saklanan fotoğrafın uzun kenarı en fazla bu kadar; avatar zaten küçük (ör. 368x560).
IMAGE_MAX_SIDE = 1536
ACCEPTED_TYPES: dict[tuple[Kind, FileRole], frozenset[str]] = {
    ("voice", "sample"): AUDIO_TYPES,
    ("face", "sample"): VIDEO_TYPES | IMAGE_TYPES,
    ("voice", "consent_recording"): VIDEO_TYPES,
    ("face", "consent_recording"): VIDEO_TYPES,
}
_ASSET_KIND: dict[Kind, str] = {"voice": "voice", "face": "avatar"}


class BiometricError(Exception):
    """Kullanıcıya gösterilebilir hata; ``code`` istemcinin çevirdiği kısa koddur."""

    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class EnrollmentNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class EnrollmentView:
    enrollment: BiometricEnrollment
    files: list[EnrollmentSample]
    consent_sentence: str


# --- yardımcılar ------------------------------------------------------------------


def normalize_media_type(content_type: str | None) -> str:
    """'audio/webm;codecs=opus' -> 'audio/webm'."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def sniff_container(data: bytes) -> str | None:
    """Dosyanın gerçek türü, ilk baytlarına ("sihirli baytlar") bakarak. Content-Type
    başlığına güvenilmez; tarayıcı/saldırgan istediğini yazabilir."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"  # EBML (WebM/Matroska)
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[4:8] == b"ftyp":
        return "mp4"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mpeg"
    return None


def _container_of(media_type: str) -> str:
    return media_type.split("/", 1)[1] if "/" in media_type else ""


def normalize_face_image(data: bytes) -> bytes:
    """Yüz fotoğrafını gerçekten çözüp PNG olarak yeniden kodlar.

    Böylece EXIF/konum bilgisi ve görselin içine gizlenmiş başka veri atılır (§11.7), telefonun
    döndürme bilgisi uygulanır ve çözülemeyen (sahte) dosyalar reddedilir.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > IMAGE_MAX_PIXELS:
                raise BiometricError("image_too_large", status=413)
            image.load()
            upright = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise BiometricError("image_unreadable", status=422) from exc
    upright.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))
    out = io.BytesIO()
    upright.save(out, format="PNG")
    return out.getvalue()


def provider_available(settings: Settings, registry: ProviderRegistry, kind: Kind) -> bool:
    """Gerçek ortamda sahte (mock) sağlayıcıyla klon "oluşturulmuş gibi" yapılmasın."""
    if settings.is_dev:
        return True
    feature: ProviderKind = "voice_enrollment" if kind == "voice" else "avatar_enrollment"
    return registry.provider_name(feature, "default") != "mock"


async def _open_enrollment(
    db: AsyncSession, user_id: uuid.UUID, kind: Kind
) -> BiometricEnrollment | None:
    result = await db.execute(
        select(BiometricEnrollment).where(
            BiometricEnrollment.user_id == user_id,
            BiometricEnrollment.kind == kind,
            BiometricEnrollment.status.in_(OPEN_STATUSES),
        )
    )
    return result.scalars().first()


async def _files(db: AsyncSession, enrollment_id: uuid.UUID) -> list[EnrollmentSample]:
    result = await db.execute(
        select(EnrollmentSample)
        .where(EnrollmentSample.enrollment_id == enrollment_id)
        .order_by(EnrollmentSample.created_at)
    )
    return list(result.scalars().all())


async def _consent(db: AsyncSession, enrollment_id: uuid.UUID) -> Consent | None:
    result = await db.execute(select(Consent).where(Consent.enrollment_id == enrollment_id))
    return result.scalar_one_or_none()


def _kind(enrollment: BiometricEnrollment) -> Kind:
    return "face" if enrollment.kind == "face" else "voice"


async def view(db: AsyncSession, enrollment: BiometricEnrollment, owner: User) -> EnrollmentView:
    return EnrollmentView(
        enrollment=enrollment,
        files=await _files(db, enrollment.id),
        consent_sentence=consent_texts.sentence(
            _kind(enrollment),
            owner.locale,
            name=owner.display_name,
            code=enrollment.challenge_code,
        ),
    )


# --- kullanıcı tarafı -------------------------------------------------------------


async def start(
    db: AsyncSession,
    settings: Settings,
    registry: ProviderRegistry,
    user: User,
    *,
    kind: Kind,
    accepted_version: str,
) -> BiometricEnrollment:
    if accepted_version != consent_texts.VERSION:
        raise BiometricError("consent_text_outdated")
    if not provider_available(settings, registry, kind):
        raise BiometricError("enrollment_unavailable", status=503)
    if await _open_enrollment(db, user.id, kind) is not None:
        raise BiometricError("enrollment_exists")
    enrollment = BiometricEnrollment(
        user_id=user.id,
        kind=kind,
        challenge_code=f"{secrets.randbelow(1_000_000):06d}",
        consent_text_version=consent_texts.VERSION,
    )
    db.add(enrollment)
    await db.flush()
    audit.record(
        db,
        action="biometric.enrollment_started",
        target_type="biometric_enrollment",
        target_id=enrollment.id,
        user_id=user.id,
        actor_id=user.id,
        meta={"kind": kind},
    )
    await db.commit()
    return enrollment


async def list_for_user(db: AsyncSession, user: User) -> list[BiometricEnrollment]:
    result = await db.execute(
        select(BiometricEnrollment)
        .where(BiometricEnrollment.user_id == user.id)
        .order_by(BiometricEnrollment.created_at.desc())
    )
    return list(result.scalars().all())


async def get_for_user(
    db: AsyncSession, user: User, enrollment_id: uuid.UUID
) -> BiometricEnrollment:
    """Sahiplik sorgunun içinde: başkasının kaydı bizim için "yok" (IDOR'a karşı)."""
    result = await db.execute(
        select(BiometricEnrollment).where(
            BiometricEnrollment.id == enrollment_id, BiometricEnrollment.user_id == user.id
        )
    )
    enrollment = result.scalar_one_or_none()
    if enrollment is None:
        raise EnrollmentNotFoundError(str(enrollment_id))
    return enrollment


async def add_file(
    db: AsyncSession,
    store: EncryptedStore,
    user: User,
    enrollment: BiometricEnrollment,
    *,
    role: FileRole,
    media_type: str,
    data: bytes,
    duration_s: int | None,
) -> EnrollmentSample:
    if enrollment.status != "collecting":
        raise BiometricError("enrollment_not_collecting")
    kind = _kind(enrollment)
    if len(data) > SIZE_LIMITS[(kind, role)]:
        raise BiometricError("file_too_large", status=413)
    if not data:
        raise BiometricError("file_empty", status=422)
    if media_type not in ACCEPTED_TYPES[(kind, role)]:
        raise BiometricError("unsupported_media_type", status=415)
    if sniff_container(data) != _container_of(media_type):
        raise BiometricError("media_type_mismatch", status=415)
    if media_type in IMAGE_TYPES:
        if len(data) > IMAGE_SIZE_LIMIT:
            raise BiometricError("file_too_large", status=413)
        # Görsel çözmek işlemciyi meşgul eder; sunucu diğer isteklere bakabilsin.
        data = await asyncio.to_thread(normalize_face_image, data)
        media_type = "image/png"
        duration_s = None

    existing = await _files(db, enrollment.id)
    if role == "sample" and sum(f.role == "sample" for f in existing) >= MAX_SAMPLES:
        raise BiometricError("too_many_samples")
    if role == "consent_recording":
        # Tek rıza videosu: yenisi eskisinin yerine geçer (yeniden çekim).
        for old in (f for f in existing if f.role == "consent_recording"):
            await store.delete("biometric", old.blob_key)
            await db.delete(old)

    file_id = uuid.uuid4()
    blob_key = f"{user.id}/{enrollment.id}/{file_id}"
    await store.put(db, user.id, "biometric", blob_key, data)
    sample = EnrollmentSample(
        id=file_id,
        enrollment_id=enrollment.id,
        user_id=user.id,
        role=role,
        blob_key=blob_key,
        media_type=media_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        duration_s=duration_s,
    )
    db.add(sample)
    await db.commit()
    return sample


async def delete_file(
    db: AsyncSession,
    store: EncryptedStore,
    enrollment: BiometricEnrollment,
    file_id: uuid.UUID,
) -> None:
    if enrollment.status != "collecting":
        raise BiometricError("enrollment_not_collecting")
    result = await db.execute(
        select(EnrollmentSample).where(
            EnrollmentSample.id == file_id, EnrollmentSample.enrollment_id == enrollment.id
        )
    )
    sample = result.scalar_one_or_none()
    if sample is None:
        raise EnrollmentNotFoundError(str(file_id))
    await store.delete("biometric", sample.blob_key)
    await db.delete(sample)
    await db.commit()


async def submit(db: AsyncSession, user: User, enrollment: BiometricEnrollment) -> None:
    """Örnekler + rıza videosu tamamsa incelemeye gönderir ve değiştirilemez rıza kaydını yazar."""
    if enrollment.status != "collecting":
        raise BiometricError("enrollment_not_collecting")
    files = await _files(db, enrollment.id)
    samples = [f for f in files if f.role == "sample"]
    consent_video = next((f for f in files if f.role == "consent_recording"), None)
    if not samples:
        raise BiometricError("samples_missing", status=422)
    if consent_video is None:
        raise BiometricError("consent_recording_missing", status=422)

    kind = _kind(enrollment)
    now = utcnow()
    enrollment.status = "pending_review"
    enrollment.submitted_at = now
    consent = Consent(
        user_id=user.id,
        purpose=consent_texts.PURPOSE[kind],
        enrollment_id=enrollment.id,
        text_version=enrollment.consent_text_version,
        status="granted",
        granted_at=now,
    )
    db.add(consent)
    await db.flush()
    db.add(
        ConsentRecord(
            consent_id=consent.id,
            user_id=user.id,
            event="granted",
            actor_id=user.id,
            text_version=enrollment.consent_text_version,
            text_sha256=consent_texts.text_digest(
                kind, user.locale, name=user.display_name, code=enrollment.challenge_code
            ),
            evidence_sha256=consent_video.sha256,
        )
    )
    audit.record(
        db,
        action="biometric.submitted",
        target_type="biometric_enrollment",
        target_id=enrollment.id,
        user_id=user.id,
        actor_id=user.id,
        meta={"kind": kind, "samples": len(samples)},
    )
    await db.commit()


async def revoke(db: AsyncSession, user: User, enrollment: BiometricEnrollment) -> None:
    """Rızayı geri alır / kaydı iptal eder. Kullanım bu istekte durur; silme işi sıraya girer.
    Tekrar çağrılırsa bir şey yapmaz."""
    if enrollment.status not in OPEN_STATUSES:
        return
    now = utcnow()
    enrollment.status = "revoked"
    enrollment.revoked_at = now
    consent = await _consent(db, enrollment.id)
    if consent is not None and consent.status == "granted":
        consent.status = "revoked"
        consent.revoked_at = now
        db.add(_record(consent, "revoked", actor_id=user.id))
    audit.record(
        db,
        action="biometric.revoked",
        target_type="biometric_enrollment",
        target_id=enrollment.id,
        user_id=user.id,
        actor_id=user.id,
        meta={"kind": enrollment.kind},
    )
    await queue.enqueue(db, BIOMETRIC_PURGE, {"enrollment_id": str(enrollment.id)})
    await db.commit()


def _record(consent: Consent, event: str, *, actor_id: uuid.UUID | None) -> ConsentRecord:
    return ConsentRecord(
        consent_id=consent.id,
        user_id=consent.user_id,
        event=event,
        actor_id=actor_id,
        text_version=consent.text_version,
        # Olay kaydı: metnin kendisi "granted" kaydında; burada sürümün özeti yeter.
        text_sha256=hashlib.sha256(consent.text_version.encode()).hexdigest(),
    )


async def active_asset(db: AsyncSession, user_id: uuid.UUID, kind: Kind) -> ProviderAsset | None:
    """Kullanıcının o türdeki **şu an** kullanılabilir klonu. Her kullanımda yeniden sorulur;
    rıza geri alındığı an None döner (§11.3 "kullanım anında durur")."""
    result = await db.execute(
        select(ProviderAsset)
        .join(BiometricEnrollment, BiometricEnrollment.id == ProviderAsset.enrollment_id)
        .join(Consent, Consent.enrollment_id == BiometricEnrollment.id)
        .where(
            BiometricEnrollment.user_id == user_id,
            BiometricEnrollment.kind == kind,
            BiometricEnrollment.status == "active",
            Consent.status == "granted",
            ProviderAsset.status == "active",
        )
    )
    return result.scalars().first()


@dataclass(frozen=True, slots=True)
class FacePhoto:
    data: bytes
    media_type: str


async def face_photo(
    db: AsyncSession, store: EncryptedStore, user_id: uuid.UUID, enrollment_id: uuid.UUID
) -> FacePhoto | None:
    """Aktif yüz kaydının en son yüklenen fotoğrafı (fotoğraftan çalışan avatarlar için).
    Her kullanım denetim kaydına yazılır: biyometrik veri kimin için ne zaman açıldı."""
    sample = await db.scalar(
        select(EnrollmentSample)
        .where(
            EnrollmentSample.enrollment_id == enrollment_id,
            EnrollmentSample.user_id == user_id,
            EnrollmentSample.role == "sample",
            EnrollmentSample.media_type.in_(IMAGE_TYPES),
        )
        .order_by(EnrollmentSample.created_at.desc())
        .limit(1)
    )
    if sample is None:
        return None
    data = await store.get(db, user_id, "biometric", sample.blob_key)
    audit.record(
        db,
        action="biometric.used",
        target_type="biometric_enrollment",
        target_id=enrollment_id,
        user_id=user_id,
        actor_id=user_id,
        meta={"kind": "face", "use": "avatar_session"},
    )
    await db.commit()
    return FacePhoto(data, sample.media_type)


# --- inceleme (admin) -------------------------------------------------------------


async def pending_reviews(db: AsyncSession) -> list[BiometricEnrollment]:
    result = await db.execute(
        select(BiometricEnrollment)
        .where(BiometricEnrollment.status == "pending_review")
        .order_by(BiometricEnrollment.submitted_at)
    )
    return list(result.scalars().all())


async def get_any(db: AsyncSession, enrollment_id: uuid.UUID) -> BiometricEnrollment:
    enrollment = await db.get(BiometricEnrollment, enrollment_id)
    if enrollment is None:
        raise EnrollmentNotFoundError(str(enrollment_id))
    return enrollment


def _check_reviewer(settings: Settings, reviewer: User, enrollment: BiometricEnrollment) -> bool:
    """Görevler ayrılığı: kimse kendi kaydını onaylayamaz. Tek kişilik geliştirmede (dev)
    izinli, ama denetim kaydında işaretlenir. Dönüş: kendi kaydı mı."""
    own = enrollment.user_id == reviewer.id
    if own and not settings.is_dev:
        raise BiometricError("self_review_forbidden", status=403)
    return own


async def approve(
    db: AsyncSession, settings: Settings, reviewer: User, enrollment: BiometricEnrollment
) -> None:
    if enrollment.status != "pending_review":
        raise BiometricError("enrollment_not_pending")
    own = _check_reviewer(settings, reviewer, enrollment)
    enrollment.status = "processing"
    enrollment.reviewed_at = utcnow()
    enrollment.reviewer_id = reviewer.id
    consent = await _consent(db, enrollment.id)
    if consent is not None:
        db.add(_record(consent, "approved", actor_id=reviewer.id))
    audit.record(
        db,
        action="biometric.approved",
        target_type="biometric_enrollment",
        target_id=enrollment.id,
        user_id=enrollment.user_id,
        actor_id=reviewer.id,
        meta={"kind": enrollment.kind, "self_review": own},
    )
    await queue.enqueue(db, BIOMETRIC_CREATE_ASSET, {"enrollment_id": str(enrollment.id)})
    await db.commit()


async def reject(
    db: AsyncSession,
    settings: Settings,
    reviewer: User,
    enrollment: BiometricEnrollment,
    reason: RejectReason,
) -> None:
    if enrollment.status != "pending_review":
        raise BiometricError("enrollment_not_pending")
    own = _check_reviewer(settings, reviewer, enrollment)
    now = utcnow()
    enrollment.status = "rejected"
    enrollment.reviewed_at = now
    enrollment.reviewer_id = reviewer.id
    enrollment.reject_reason = reason
    consent = await _consent(db, enrollment.id)
    if consent is not None:
        consent.status = "revoked"
        consent.revoked_at = now
        db.add(_record(consent, "rejected", actor_id=reviewer.id))
    audit.record(
        db,
        action="biometric.rejected",
        target_type="biometric_enrollment",
        target_id=enrollment.id,
        user_id=enrollment.user_id,
        actor_id=reviewer.id,
        meta={"kind": enrollment.kind, "reason": reason, "self_review": own},
    )
    await queue.enqueue(db, BIOMETRIC_PURGE, {"enrollment_id": str(enrollment.id)})
    await db.commit()


async def read_file_for_review(
    db: AsyncSession,
    store: EncryptedStore,
    reviewer: User,
    enrollment: BiometricEnrollment,
    file_id: uuid.UUID,
) -> tuple[bytes, str]:
    """İnceleyici bir dosyayı açar; her açılış denetim kaydına yazılır."""
    result = await db.execute(
        select(EnrollmentSample).where(
            EnrollmentSample.id == file_id, EnrollmentSample.enrollment_id == enrollment.id
        )
    )
    sample = result.scalar_one_or_none()
    if sample is None:
        raise EnrollmentNotFoundError(str(file_id))
    data = await store.get(db, enrollment.user_id, "biometric", sample.blob_key)
    audit.record(
        db,
        action="biometric.file_viewed",
        target_type="enrollment_sample",
        target_id=sample.id,
        user_id=enrollment.user_id,
        actor_id=reviewer.id,
        meta={"role": sample.role},
    )
    await db.commit()
    return data, sample.media_type


async def sample_count(
    db: AsyncSession, enrollment_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not enrollment_ids:
        return {}
    result = await db.execute(
        select(EnrollmentSample.enrollment_id, func.count())
        .where(EnrollmentSample.enrollment_id.in_(enrollment_ids))
        .group_by(EnrollmentSample.enrollment_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


def asset_kind(kind: Kind) -> str:
    return _ASSET_KIND[kind]


# --- önizleme ---------------------------------------------------------------------


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Ham 16 bit mono PCM'i tarayıcının çalabileceği WAV dosyasına sarar."""
    header = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt "
    header += (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    header += sample_rate.to_bytes(4, "little") + (sample_rate * 2).to_bytes(4, "little")
    header += (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    return header + b"data" + len(pcm).to_bytes(4, "little") + pcm


async def voice_preview(
    db: AsyncSession, registry: ProviderRegistry, user: User, sentence_index: int
) -> bytes:
    """Kullanıcının kendi klon sesiyle, yalnızca sabit cümlelerden birini seslendirir."""
    sentences = consent_texts.PREVIEW_SENTENCES["en" if user.locale == "en" else "tr"]
    if sentence_index >= len(sentences):
        raise BiometricError("unknown_sentence", status=422)
    asset = await active_asset(db, user.id, "voice")
    if asset is None:
        raise BiometricError("no_active_voice")
    tts = registry.tts("preview")
    if tts.name != asset.provider:
        raise BiometricError("preview_unavailable", status=503)
    fmt = AudioFormat(sample_rate=24_000)

    async def text() -> AsyncIterator[str]:
        yield sentences[sentence_index]

    request = TTSRequest(voice_id=asset.asset_id, language=user.locale, output=fmt)
    pcm = b"".join([chunk.data async for chunk in tts.synthesize(text(), request)])
    audit.record(
        db,
        action="biometric.voice_preview",
        target_type="provider_asset",
        target_id=asset.id,
        user_id=user.id,
        actor_id=user.id,
        meta={"sentence": sentence_index},
    )
    await db.commit()
    return pcm_to_wav(pcm, fmt.sample_rate)
