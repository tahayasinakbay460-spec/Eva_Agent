"""EVA'nın sesli görüşme ajanı (LiveKit Agents; CLAUDE.md §4.3, Faz 2).

Akış: tarayıcı odaya girer → LiveKit, token'daki çağrıyla bu ajanı odaya gönderir → ajan
görüşme kaydını açar → kullanıcıyı dinler (VAD + Türkçe tur sonu modeli) → konuşma bitince
cevabı LLM'den akıtır → TTS ilk kelimelerle başlar → kullanıcı söze girerse anında susar.

Her tur veritabanına yazılır (``CallTurns``): kullanıcının sözü, EVA'nın söyleyebildiği kadarı
(kesildiyse işaretli) ve aşama süreleri. Görüşme bitince anı çıkarma sıraya girer.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    TurnHandlingOptions,
    inference,
    llm,
    room_io,
)
from livekit.plugins import silero
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.database import create_engine, create_session_factory
from app.persona.compiler import PersonaCompiler
from app.providers.base import AvatarSessionRequest, LLMRequest, MediaRoom
from app.providers.registry import ProviderRegistry, build_registry
from app.services.chat_service import ChatService
from app.services.voice_service import CallTurns, EndReason, TurnTimings
from eva_realtime.adapters import EvaLLM, EvaSTT, EvaTTS
from eva_realtime.avatar import AvatarBridge, mint_avatar_token, room_avatar_output

log = logging.getLogger("eva.realtime")

# LiveKit odasındaki ses 24 kHz; avatar (LiveAvatar) da 24 kHz PCM istiyor.
OUTPUT_SAMPLE_RATE = 24_000


@dataclass(frozen=True, slots=True)
class Runtime:
    """Süreç başına bir kez kurulan paylaşılan parçalar."""

    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    registry: ProviderRegistry
    turns: CallTurns


@lru_cache
def runtime() -> Runtime:
    settings = get_settings()
    registry = build_registry(settings)
    chat = ChatService(registry=registry, compiler=PersonaCompiler(), settings=settings)
    return Runtime(
        settings=settings,
        session_factory=create_session_factory(create_engine(settings.database_url)),
        registry=registry,
        turns=CallTurns(chat),
    )


def parse_call_id(metadata: str | None) -> uuid.UUID:
    """Ajan çağrısının içindeki görüşme id'si. Bu bilgi API'nin imzaladığı token'dan gelir;
    tarayıcı değiştiremez."""
    data = json.loads(metadata or "{}")
    return uuid.UUID(str(data["call_id"]))


def timings_from(
    user_metrics: dict[str, Any], reply_metrics: dict[str, Any], *, avatar: bool = False
) -> TurnTimings:
    """LiveKit'in saniye cinsinden ölçümlerini bizim milisaniyelik tur kaydımıza çevirir."""

    def ms(source: dict[str, Any], key: str) -> float | None:
        value = source.get(key)
        return round(float(value) * 1000, 1) if isinstance(value, int | float) else None

    return TurnTimings(
        end_of_turn_ms=ms(user_metrics, "end_of_turn_delay"),
        stt_final_ms=ms(user_metrics, "transcription_delay"),
        llm_ttft_ms=ms(reply_metrics, "llm_node_ttft"),
        tts_ttfb_ms=ms(reply_metrics, "tts_node_ttfb"),
        e2e_ms=ms(reply_metrics, "e2e_latency"),
        # Avatar varken "oynatma başladı" = avatarın ilk konuşan karesi kullanıcıya gitti.
        avatar_first_frame_ms=ms(reply_metrics, "playback_latency") if avatar else None,
    )


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    # Ses aktivitesi modeli (VAD) her görüşmede yeniden yüklenmesin (ısınma, §4.3).
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=get_settings().voice_agent_name)
async def entrypoint(ctx: JobContext) -> None:
    rt = runtime()
    call_id = parse_call_id(ctx.job.metadata)
    stt_provider = rt.registry.stt("realtime")
    tts_provider = rt.registry.tts("realtime")
    llm_provider, _ = rt.registry.llm("realtime")
    avatar_provider = rt.registry.avatar("realtime")

    async with rt.session_factory() as db:
        call = await rt.turns.open(db, call_id)
        # Sahte (mock) avatar görüntü üretmez: o durumda görüntülü görüşme sesli devam eder.
        use_avatar = call.mode == "video" and avatar_provider.name != "mock"
        media = await rt.turns.call_media(
            db,
            call_id,
            media_config=rt.settings.media_config,
            tts_provider=tts_provider.name,
            avatar_provider=avatar_provider.name if use_avatar else None,
        )

    async def prepare(item_id: str | None, text: str | None) -> LLMRequest:
        async with rt.session_factory() as db:
            # Kendi klonuyla görüşmede rıza her turda yeniden kontrol edilir (§11.3).
            if not await rt.turns.media_still_allowed(db, call_id):
                finish("consent_revoked")
                raise RuntimeError("consent revoked during call")
            return await rt.turns.prepare_reply(db, call_id, user_item_id=item_id, user_text=text)

    eva_stt = EvaSTT(stt_provider)
    session: AgentSession[None] = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=eva_stt,
        llm=EvaLLM(llm_provider, prepare),
        tts=EvaTTS(tts_provider, voice_id=media.voice_id, sample_rate=OUTPUT_SAMPLE_RATE),
        turn_handling=TurnHandlingOptions(
            # Türkçe destekli ses tabanlı tur sonu modeli; kendi sunucumuzda CPU'da çalışır.
            turn_detection=inference.TurnDetector(),
            interruption={"enabled": True, "mode": "vad"},
            # Kullanıcı bitirmeden cevap üretmeye başlama: boşa token harcar (ölçünce açılabilir).
            preemptive_generation={"enabled": False},
        ),
        user_away_timeout=float(call.idle_timeout_s),
    )

    end_reason: list[EndReason] = ["disconnected"]
    pending: set[asyncio.Task[None]] = set()
    last_user_metrics: dict[str, Any] = {}

    def finish(reason: EndReason) -> None:
        end_reason[0] = reason
        session.shutdown(drain=reason != "error")

    @session.on("user_state_changed")
    def _on_user_state(ev: Any) -> None:
        if ev.old_state == "speaking" and ev.new_state == "listening":
            eva_stt.mark_speech_end()  # VAD: kullanıcı sustu → STT bölümü kesinleştirsin
        elif ev.new_state == "away":
            finish("idle")

    @session.on("conversation_item_added")
    def _on_item(ev: Any) -> None:
        item = ev.item
        if not isinstance(item, llm.ChatMessage):
            return
        if item.role == "user":
            last_user_metrics.clear()
            last_user_metrics.update(dict(item.metrics))
            return
        if item.role != "assistant":
            return

        async def save() -> None:
            async with rt.session_factory() as db:
                await rt.turns.save_reply(
                    db,
                    call_id,
                    item_id=item.id,
                    text=item.text_content or "",
                    interrupted=item.interrupted,
                    timings=timings_from(last_user_metrics, dict(item.metrics), avatar=use_avatar),
                )

        task = asyncio.create_task(save())
        pending.add(task)
        task.add_done_callback(pending.discard)

    @session.on("error")
    def _on_error(ev: Any) -> None:
        if not getattr(ev.error, "recoverable", True):
            log.warning("realtime session error", extra={"source": type(ev.source).__name__})
            finish("error")

    async def on_shutdown() -> None:
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        async with rt.session_factory() as db:
            await rt.turns.close(db, call_id, end_reason[0])

    ctx.add_shutdown_callback(on_shutdown)

    # Sadece belli bir katılımcıyı dinlemek için önce odaya bağlanmak gerekiyor.
    await ctx.connect()

    if use_avatar and media.avatar_id:
        # Avatar bizim odamıza katılır; token'ını biz üretiriz (sağlayıcıya anahtar verilmez).
        token = mint_avatar_token(
            rt.settings,
            room_name=ctx.room.name,
            agent_identity=ctx.room.local_participant.identity,
        )
        avatar_session = await avatar_provider.start_session(
            AvatarSessionRequest(
                avatar_id=media.avatar_id,
                room_name=ctx.room.name,
                max_duration_s=call.max_duration_s,
                idle_timeout_s=call.idle_timeout_s,
                room=MediaRoom(
                    url=str(rt.settings.livekit_url), token=token, session_id=await ctx.room.sid
                ),
            )
        )
        if avatar_session.audio_via_room:
            # Anam gibi: ses odanın avatar kanalından gider; oda kapanınca avatar da çıkar.
            session.output.replace_audio_tail(room_avatar_output(ctx.room, avatar_session))
            ctx.add_shutdown_callback(avatar_session.close)
        else:
            bridge = AvatarBridge(avatar_session)
            await bridge.attach(session.output.replace_audio_tail)
            ctx.add_shutdown_callback(bridge.aclose)
    await session.start(
        agent=Agent(instructions=""),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            # Sadece token'ı alan kullanıcının sesi dinlenir; odaya başka biri girse de duyulmaz.
            participant_identity=f"user-{call.user_id}",
            text_input=False,
            close_on_disconnect=True,
            delete_room_on_close=True,
        ),
    )

    async def max_duration_guard() -> None:
        await asyncio.sleep(call.max_duration_s)
        finish("max_duration")

    guard = asyncio.create_task(max_duration_guard())
    ctx.add_shutdown_callback(lambda: _cancel(guard))
    session.generate_reply()  # açılış selamı


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
