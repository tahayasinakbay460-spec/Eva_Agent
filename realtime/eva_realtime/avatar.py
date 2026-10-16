"""Görüntülü görüşmede EVA'nın sesini avatara yönlendiren köprü (Faz 3; CLAUDE.md §4.3).

Normalde ajan TTS sesini doğrudan odaya basar. Görüntülü görüşmede ses önce avatara gider;
avatar (LiveAvatar LITE) dudak senkronlu videoyu **ve** sesi odaya kendisi yayınlar, böylece
kullanıcı ikisini birlikte duyar/görür (sesi iki kez duymaz).

LiveKit'e "ne kadarını söyledi" bilgisini avatar verir: avatar konuşmaya başlayınca / bitirince
gelen olaylar LiveKit'e iletilir. Kullanıcı söze girince LiveKit tamponu temizler; köprü avatara
``interrupt`` gönderir ve kesilen sözü bildirir.
"""

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any

from livekit import api, rtc
from livekit.agents.voice.avatar import AudioSegmentEnd, QueueAudioOutput
from livekit.agents.voice.io import AudioOutput
from livekit.agents.voice.room_io import ATTRIBUTE_PUBLISH_ON_BEHALF

from app.core.config import Settings
from app.providers.base import AudioChunk, AvatarPlaybackStarted, AvatarSession

AVATAR_IDENTITY = "eva-avatar"


def mint_avatar_token(settings: Settings, *, room_name: str, agent_identity: str) -> str:
    """Avatar katılımcısı için tek odaya giriş token'ı. "agent" türünde ve ajan adına yayın
    yapıyor olarak işaretli: LiveKit avatarın görüntüsünü/sesini EVA'nın çıktısı sayar."""
    if not settings.livekit_api_key or settings.livekit_api_secret is None:
        raise RuntimeError("livekit is not configured")
    return (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret.get_secret_value())
        .with_kind("agent")
        .with_identity(AVATAR_IDENTITY)
        .with_name("EVA")
        .with_ttl(timedelta(minutes=5))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_attributes({ATTRIBUTE_PUBLISH_ON_BEHALF: agent_identity})
        .to_jwt()
    )


class AvatarBridge:
    def __init__(self, avatar: AvatarSession) -> None:
        self._avatar = avatar
        self._format = avatar.input_format
        self.audio_output = QueueAudioOutput(
            sample_rate=self._format.sample_rate, wait_playback_start=True
        )
        self._resampler: rtc.AudioResampler | None = None
        self._position = 0.0  # bu sözde avatara gönderilen ses (saniye)
        self._playing = False
        self._tasks: set[asyncio.Task[None]] = set()

    async def attach(self, replace_audio_tail: Callable[[AudioOutput], None]) -> None:
        """Ajanın ses çıkışının sonuna köprüyü takar (``session.output.replace_audio_tail``)."""
        await self.audio_output.start()
        # "clear_buffer" QueueAudioOutput'un kendi olayı; üst sınıfın tip listesinde yok.
        self.audio_output.on("clear_buffer", self._on_clear)  # type: ignore[arg-type]
        replace_audio_tail(self.audio_output)
        self._spawn(self._forward())
        self._spawn(self._playback_events())

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _frames(self, frame: rtc.AudioFrame) -> list[rtc.AudioFrame]:
        if frame.sample_rate == self._format.sample_rate and frame.num_channels == 1:
            return [frame]
        if self._resampler is None:
            self._resampler = rtc.AudioResampler(
                input_rate=frame.sample_rate, output_rate=self._format.sample_rate, num_channels=1
            )
        return list(self._resampler.push(frame))

    async def _forward(self) -> None:
        async for item in self.audio_output:
            if isinstance(item, AudioSegmentEnd):
                await self._avatar.end_of_speech()
                continue
            for frame in self._frames(item):
                self._playing = True
                self._position += frame.duration
                await self._avatar.send_audio(AudioChunk(frame.data.tobytes(), self._format))

    async def _playback_events(self) -> None:
        async for event in self._avatar.events():
            if isinstance(event, AvatarPlaybackStarted):
                self.audio_output.notify_playback_started()
            elif not event.interrupted and self._playing:
                # Kesilen sözler _on_clear'da bildirilir; burada sadece sonuna kadar söylenenler.
                self._playing = False
                self.audio_output.notify_playback_finished(
                    playback_position=self._position, interrupted=False
                )
                self._position = 0.0

    def _on_clear(self) -> None:
        was_playing, position = self._playing, self._position
        self._playing = False
        self._position = 0.0

        async def interrupt() -> None:
            await self._avatar.interrupt()
            if was_playing:
                self.audio_output.notify_playback_finished(
                    playback_position=position, interrupted=True
                )

        self._spawn(interrupt())

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await self._avatar.close()
        await self.audio_output.aclose()
