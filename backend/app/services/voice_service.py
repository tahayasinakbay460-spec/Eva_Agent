"""Sesli/görüntülü görüşme (CLAUDE.md §4.3, §5.3; Faz 2).

İki taraf var:

- **API tarafı** (``start_call``, ``end_call``, gecikme özeti): kullanıcı "ara"ya basınca bir
  görüşme kaydı açar ve tarayıcıya LiveKit odası için kısa ömürlü, tek odaya bağlı bir token
  verir. Ajanı (``realtime/``) token'ın içine gömülü "dispatch" çağırır; ajan görüşmenin
  id'sini oradan okur — tarayıcı bunu değiştiremez.
- **Ajan tarafı** (``CallTurns``): her turda kullanıcının sözünü kaydeder, EVA'nın cevabı için
  LLM isteğini metin sohbetiyle aynı yoldan kurar (aynı persona, aynı hafıza, aynı geçmiş;
  kanal değişse de konuşma kaldığı yerden sürer, §5.3), cevabı (yarıda kesildiyse "kesildi"
  işaretiyle) ve tur sürelerini yazar.

Sıcak yol kuralı aynı: bir geçmiş okuma, bir hafıza sorgusu, bir LLM akışı (§2.7).
"""

import json
import secrets
import statistics
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from livekit import api as lk_api
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database import utcnow, utcnow_after
from app.models.call import CallSession, TurnLatency
from app.models.conversation import Conversation, Message
from app.models.persona import Persona
from app.models.user import User
from app.persona.media import (
    FILE_PREFIX,
    OWN,
    PERSONA_FACE,
    MediaNotConfiguredError,
    load_catalog,
    media_image,
)
from app.providers.base import EnrollmentSample, LLMRequest
from app.providers.registry import ProviderRegistry
from app.services import (
    biometric_service,
    character_service,
    media_service,
    memory_extraction,
    memory_retrieval,
    persona_service,
)
from app.services.chat_service import ChatService
from app.storage.encrypted import EncryptedStore

CallMode = Literal["voice", "video"]
EndReason = Literal[
    "user", "idle", "max_duration", "disconnected", "replaced", "error", "consent_revoked"
]

# Görüşme açılınca EVA'nın ilk sözü için sahte "kullanıcı turu" (kaydedilmez).
CALL_OPENING_CUE = (
    "(Sesli görüşme şimdi başladı. Kullanıcıyı kısaca, doğal bir şekilde selamla; "
    "konuşmanın geçmişi varsa ona uygun bir giriş yap.)"
)


class VoiceNotConfiguredError(RuntimeError):
    pass


class VideoQuotaExceededError(RuntimeError):
    pass


class CallNotFoundError(LookupError):
    pass


class MediaNotReadyError(RuntimeError):
    """Kendi sesinle/yüzünle görüşme istendi ama aktif (onaylı, rızası geçerli) klon yok."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CallMedia:
    """Bu görüşmede EVA hangi sesle konuşacak, hangi yüzle görünecek (sağlayıcıdaki id'ler)."""

    voice_id: str
    avatar_id: str | None
    # Fotoğraftan çalışan avatar (ör. LemonSlice) için kullanıcının rızalı yüz fotoğrafı.
    avatar_image: EnrollmentSample | None = None


@dataclass(frozen=True, slots=True)
class StartedCall:
    call: CallSession
    url: str
    token: str


# --- API tarafı -----------------------------------------------------------------


async def start_call(
    db: AsyncSession,
    settings: Settings,
    user: User,
    *,
    persona_id: uuid.UUID | None,
    mode: CallMode,
    registry: ProviderRegistry,
) -> StartedCall:
    if not settings.voice_configured:
        raise VoiceNotConfiguredError
    if persona_id is None:
        persona = await persona_service.get_default_eva(db)
    else:
        persona = await persona_service.get_persona_for_user(db, user, persona_id)

    # Kullanıcının seçtiği ses ve yüz (seçmediyse personanın varsayılanı). "Kendi" seçildiyse
    # rızalı kayıt şu an aktif olmalı; görüşme boyunca her turda yeniden kontrol edilir.
    choice = await media_service.chosen(db, settings, registry, user, persona)
    if choice.voice == OWN and await biometric_service.active_asset(db, user.id, "voice") is None:
        raise MediaNotReadyError("no_active_voice")
    if (
        mode == "video"
        and choice.avatar == OWN
        and await biometric_service.active_asset(db, user.id, "face") is None
    ):
        raise MediaNotReadyError("no_active_avatar")

    max_duration = settings.voice_max_duration_s
    if mode == "video":
        remaining = settings.video_daily_quota_s - await video_seconds_today(db, user.id)
        if remaining < 30:
            raise VideoQuotaExceededError
        max_duration = min(settings.video_max_duration_s, remaining)

    # Aynı anda tek görüşme: açık kalmış eskileri kapat (sekme kapanmış olabilir).
    await db.execute(
        update(CallSession)
        .where(CallSession.user_id == user.id, CallSession.status != "ended")
        .values(status="ended", ended_at=utcnow(), end_reason="replaced")
        .execution_options(synchronize_session=False)
    )
    conversation = await _conversation_for_call(db, user, persona)
    call = CallSession(
        user_id=user.id,
        conversation_id=conversation.id,
        mode=mode,
        voice_key=choice.voice,
        avatar_key=choice.avatar if mode == "video" else None,
        room_name=f"eva-{secrets.token_hex(12)}",
        max_duration_s=max_duration,
        idle_timeout_s=settings.call_idle_timeout_s,
    )
    db.add(call)
    await db.commit()
    return StartedCall(call=call, url=str(settings.livekit_url), token=_mint_token(settings, call))


def _mint_token(settings: Settings, call: CallSession) -> str:
    """Tek odaya, kısa süreliğine giriş izni. Kullanıcı sadece mikrofonunu yayınlayabilir;
    kendi bilgilerini değiştiremez. Ajan çağrısı (dispatch) token'ın içinde, imzalı."""
    if not settings.livekit_api_key or settings.livekit_api_secret is None:
        raise VoiceNotConfiguredError
    dispatch = lk_api.RoomAgentDispatch(
        agent_name=settings.voice_agent_name,
        metadata=json.dumps({"call_id": str(call.id)}),
    )
    return (
        lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret.get_secret_value())
        .with_identity(f"user-{call.user_id}")
        .with_name("user")
        .with_ttl(timedelta(seconds=settings.call_token_ttl_s))
        .with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=call.room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=False,
                can_publish_sources=["microphone"],
                can_update_own_metadata=False,
            )
        )
        .with_room_config(lk_api.RoomConfiguration(agents=[dispatch]))
        .to_jwt()
    )


async def _conversation_for_call(db: AsyncSession, user: User, persona: Persona) -> Conversation:
    """Bu personayla en son konuşmaya devam eder (metinden sese geçince kaldığı yerden, §5.3);
    hiç yoksa yeni bir konuşma açar."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.persona_id == persona.id)
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(user_id=user.id, persona_id=persona.id, channel="voice")
        db.add(conversation)
        await db.flush()
    return conversation


async def video_seconds_today(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Bugün (UTC) görüntülü görüşmede geçen süre; bitmemiş görüşmeler şu ana kadar sayılır."""
    now = utcnow()
    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    result = await db.execute(
        select(CallSession.started_at, CallSession.ended_at).where(
            CallSession.user_id == user_id,
            CallSession.mode == "video",
            CallSession.started_at.is_not(None),
            CallSession.created_at >= day_start - timedelta(days=1),
        )
    )
    total = 0.0
    for started, ended in result.all():
        if started is None:  # pragma: no cover - sorgu bunu zaten eler
            continue
        start = max(started, day_start)
        end = ended or now
        if end > start:
            total += (end - start).total_seconds()
    return int(total)


async def get_call(db: AsyncSession, user: User, call_id: uuid.UUID) -> CallSession:
    result = await db.execute(
        select(CallSession).where(CallSession.id == call_id, CallSession.user_id == user.id)
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise CallNotFoundError(str(call_id))
    return call


async def end_call(db: AsyncSession, call: CallSession, reason: EndReason) -> None:
    """Görüşmeyi kapatır (tekrar çağrılırsa bir şey yapmaz) ve anı çıkarmayı sıraya koyar."""
    if call.status == "ended":
        return
    call.status = "ended"
    call.ended_at = utcnow()
    call.end_reason = reason
    conversation = await db.get(Conversation, call.conversation_id)
    if conversation is not None:
        # Sesli görüşme bitince beklemeden anı çıkarılsın (metinde 10 dk sessizlik bekleniyor).
        await memory_extraction.schedule(db, conversation, idle_s=0)
    await db.commit()


@dataclass(frozen=True, slots=True)
class StageSummary:
    p50: float | None
    p95: float | None
    count: int


LATENCY_STAGES = (
    "e2e_ms",
    "end_of_turn_ms",
    "stt_final_ms",
    "llm_ttft_ms",
    "tts_ttfb_ms",
    "avatar_first_frame_ms",
)


async def recent_turns(db: AsyncSession, user_id: uuid.UUID, limit: int = 100) -> list[TurnLatency]:
    result = await db.execute(
        select(TurnLatency)
        .where(TurnLatency.user_id == user_id)
        .order_by(TurnLatency.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def summarize(turns: Sequence[TurnLatency]) -> dict[str, StageSummary]:
    out: dict[str, StageSummary] = {}
    for stage in LATENCY_STAGES:
        values = sorted(v for t in turns if (v := getattr(t, stage)) is not None)
        out[stage] = StageSummary(
            p50=_percentile(values, 50), p95=_percentile(values, 95), count=len(values)
        )
    return out


def _percentile(values: Sequence[float], pct: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    return float(statistics.quantiles(values, n=100, method="inclusive")[pct - 1])


# --- ajan tarafı ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TurnTimings:
    """Bir turun aşama süreleri (milisaniye). Bilinmeyen None kalır."""

    end_of_turn_ms: float | None = None
    stt_final_ms: float | None = None
    llm_ttft_ms: float | None = None
    tts_ttfb_ms: float | None = None
    avatar_first_frame_ms: float | None = None
    e2e_ms: float | None = None


class CallTurns:
    """Gerçek zamanlı ajanın bir görüşme boyunca kullandığı veritabanı işlemleri."""

    def __init__(self, chat: ChatService) -> None:
        self._chat = chat

    async def open(self, db: AsyncSession, call_id: uuid.UUID) -> CallSession:
        """Ajan bağlanınca: görüşme geçerli mi, bitmemiş mi; öyleyse "active" yap."""
        call = await db.get(CallSession, call_id)
        if call is None or call.status == "ended":
            raise CallNotFoundError(str(call_id))
        if call.status == "created":
            call.status = "active"
            call.started_at = utcnow()
            await db.commit()
        return call

    async def persona_slug(self, db: AsyncSession, call_id: uuid.UUID) -> str:
        """Görüşmedeki personanın kısa adı (ses/yüz seçimi için; şimdilik sadece "eva")."""
        _call, _conversation, persona, _user = await self._load(db, call_id)
        return persona.slug or "eva"

    async def call_media(
        self,
        db: AsyncSession,
        call_id: uuid.UUID,
        *,
        media_config: Path,
        tts_provider: str,
        avatar_provider: str | None,
        avatar_accepts_image: bool = False,
        store: EncryptedStore | None = None,
    ) -> CallMedia:
        """Görüşmenin sesi ve (görüntülüde) yüzü: görüşme başlarken seçilen katalog sesi/yüzü
        ya da kullanıcının kendi klonu/fotoğrafı. Kendi klonuysa rıza o an kontrol edilir; klon
        başka bir sağlayıcıda oluşturulmuşsa kullanılamaz.

        Avatar sağlayıcısı fotoğraftan çalışıyorsa (``avatar_accepts_image``) kullanıcının rızalı
        fotoğrafı şifreli depodan ya da katalog görseli (``file:``) diskten okunur ve yalnızca bu
        görüşme için sağlayıcıya verilir."""
        call, _conversation, persona, user = await self._load(db, call_id)
        catalog = load_catalog(media_config)

        if call.voice_key == OWN:
            voice_asset = await biometric_service.active_asset(db, user.id, "voice")
            if voice_asset is None:
                raise MediaNotReadyError("no_active_voice")
            if voice_asset.provider != tts_provider:
                raise MediaNotReadyError("voice_provider_mismatch")
            voice_id = voice_asset.asset_id
        else:
            try:
                voice_id = catalog.provider_id("voice", call.voice_key, tts_provider)
            except MediaNotConfiguredError as exc:
                raise MediaNotReadyError("persona_media_not_configured") from exc

        if not avatar_provider:
            return CallMedia(voice_id=voice_id, avatar_id=None)

        avatar_key = call.avatar_key or catalog.default(persona.slug or "eva", "avatar")
        if avatar_key == OWN:
            avatar_asset = await biometric_service.active_asset(db, user.id, "face")
            if avatar_asset is None:
                raise MediaNotReadyError("no_active_avatar")
            if avatar_asset.provider != avatar_provider:
                raise MediaNotReadyError("avatar_provider_mismatch")
            if not avatar_accepts_image:
                return CallMedia(voice_id=voice_id, avatar_id=avatar_asset.asset_id)
            if store is None:
                raise ValueError("store is required for image avatars")
            photo = await biometric_service.face_photo(
                db, store, user.id, avatar_asset.enrollment_id
            )
            if photo is None:
                raise MediaNotReadyError("no_avatar_photo")
            return CallMedia(
                voice_id=voice_id,
                avatar_id=avatar_asset.asset_id,
                avatar_image=EnrollmentSample(photo.data, photo.media_type),
            )

        if avatar_key == PERSONA_FACE:
            # Karakterin kendi yüz görseli (ADR 0009): yalnızca görselden çalışan sağlayıcıda.
            if not avatar_accepts_image:
                raise MediaNotReadyError("persona_media_not_configured")
            if store is None:
                raise ValueError("store is required for image avatars")
            face = await character_service.face(db, store, persona)
            if face is None:
                raise MediaNotReadyError("no_persona_face")
            return CallMedia(
                voice_id=voice_id,
                avatar_id=f"persona:{persona.id}",
                avatar_image=EnrollmentSample(face.data, face.media_type),
            )

        try:
            avatar_id = catalog.provider_id("avatar", avatar_key, avatar_provider)
            image = None
            # Yerel görsel (``file:``) yalnızca fotoğraftan çalışan sağlayıcıda anlamlı.
            if avatar_id.startswith(FILE_PREFIX):
                if not avatar_accepts_image:
                    raise MediaNotConfiguredError(f"{avatar_provider} cannot use an image")
                image = media_image(media_config, avatar_id)
        except MediaNotConfiguredError as exc:
            raise MediaNotReadyError("persona_media_not_configured") from exc
        return CallMedia(voice_id=voice_id, avatar_id=avatar_id, avatar_image=image)

    async def media_still_allowed(self, db: AsyncSession, call_id: uuid.UUID) -> bool:
        """Kendi klonu/fotoğrafıyla yapılan görüşmede rıza hâlâ geçerli mi? Her turda sorulur:
        rıza geri alınırsa görüşme o an biter (§11.3 "kullanım anında durur")."""
        call = await db.get(CallSession, call_id)
        if call is None:
            return False
        if (
            call.voice_key == OWN
            and await biometric_service.active_asset(db, call.user_id, "voice") is None
        ):
            return False
        return not (
            call.mode == "video"
            and call.avatar_key == OWN
            and await biometric_service.active_asset(db, call.user_id, "face") is None
        )

    async def is_ended(self, db: AsyncSession, call_id: uuid.UUID) -> bool:
        status = await db.scalar(select(CallSession.status).where(CallSession.id == call_id))
        return status in (None, "ended")

    async def prepare_reply(
        self,
        db: AsyncSession,
        call_id: uuid.UUID,
        *,
        user_item_id: str | None,
        user_text: str | None,
    ) -> LLMRequest:
        """Kullanıcının sözünü kaydeder (aynı tur iki kez gelirse bir kez) ve EVA'nın
        cevabı için LLM isteğini kurar. ``user_text`` yoksa görüşmenin açılış selamıdır."""
        _call, conversation, persona, user = await self._load(db, call_id)
        history = await self._chat.load_history(db, conversation)
        content = CALL_OPENING_CUE
        if user_text and user_item_id:
            key = _item_key(user_item_id)
            already = next((m for m in history if m.idempotency_key == key), None)
            if already is None:
                db.add(
                    Message(
                        conversation_id=conversation.id,
                        role="user",
                        content=user_text,
                        channel="voice",
                        idempotency_key=key,
                        created_at=utcnow_after(history[-1].created_at if history else None),
                    )
                )
                conversation.updated_at = utcnow()
                await db.commit()
            else:
                history = [m for m in history if m.id != already.id]
            content = user_text
        memories = (
            await memory_retrieval.retrieve(
                db, user_id=user.id, persona_id=persona.id, query_text=user_text
            )
            if user_text
            else []
        )
        return self._chat.build_request(
            persona, user, history, content, memories, feature="realtime", channel="voice"
        )

    async def save_reply(
        self,
        db: AsyncSession,
        call_id: uuid.UUID,
        *,
        item_id: str,
        text: str,
        interrupted: bool,
        timings: TurnTimings,
    ) -> None:
        """EVA'nın söylediğini (söz kesildiyse sadece söyleyebildiği kadarını) ve tur
        sürelerini yazar. Aynı cevap iki kez gelirse bir kez kaydedilir."""
        call = await db.get(CallSession, call_id)
        if call is None:
            return
        key = _item_key(item_id)
        exists = await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == call.conversation_id, Message.idempotency_key == key)
        )
        if exists:
            return
        last = await db.scalar(
            select(func.max(Message.created_at)).where(
                Message.conversation_id == call.conversation_id
            )
        )
        if text.strip():
            db.add(
                Message(
                    conversation_id=call.conversation_id,
                    role="assistant",
                    content=text,
                    channel="voice",
                    interrupted=interrupted,
                    idempotency_key=key,
                    created_at=utcnow_after(last),
                )
            )
        db.add(
            TurnLatency(
                call_id=call.id,
                user_id=call.user_id,
                interrupted=interrupted,
                end_of_turn_ms=timings.end_of_turn_ms,
                stt_final_ms=timings.stt_final_ms,
                llm_ttft_ms=timings.llm_ttft_ms,
                tts_ttfb_ms=timings.tts_ttfb_ms,
                avatar_first_frame_ms=timings.avatar_first_frame_ms,
                e2e_ms=timings.e2e_ms,
            )
        )
        await db.commit()

    async def close(self, db: AsyncSession, call_id: uuid.UUID, reason: EndReason) -> None:
        call = await db.get(CallSession, call_id)
        if call is not None:
            await end_call(db, call, reason)

    async def _load(
        self, db: AsyncSession, call_id: uuid.UUID
    ) -> tuple[CallSession, Conversation, Persona, User]:
        call = await db.get(CallSession, call_id)
        if call is None:
            raise CallNotFoundError(str(call_id))
        conversation = await db.get(Conversation, call.conversation_id)
        user = await db.get(User, call.user_id)
        persona = (
            await db.get(Persona, conversation.persona_id) if conversation is not None else None
        )
        if conversation is None or user is None or persona is None:
            raise CallNotFoundError(str(call_id))
        return call, conversation, persona, user


def _item_key(item_id: str) -> str:
    """LiveKit'in tur id'si -> mesajın tekrar-koruma anahtarı (en fazla 64 karakter)."""
    return f"lk:{item_id}"[:64]
