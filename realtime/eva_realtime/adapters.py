"""LiveKit Agents ↔ EVA sağlayıcıları arasındaki ince köprü (CLAUDE.md §2.4, §4.2).

LiveKit'in STT/LLM/TTS sınıfları yalnızca bu dosyada görünür; içerideki işi her zaman bizim
arayüzlerimiz (``app.providers.base``) yapar. Böylece sağlayıcı değiştirmek (ElevenLabs →
kendi ses sunucumuz) bu dosyaya dokunmayı gerektirmez, sadece ``providers.yaml``'ı.

LiveKit görüşmenin "trafik polisi": sesi alır, sessizliği (VAD) ve tur sonunu tespit eder,
kullanıcı söze girince (barge-in) EVA'nın cevabını keser. Kesince buradaki akış görevleri
iptal edilir (``CancelledError``); sağlayıcı çağrıları da onunla birlikte durur.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Never

from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    llm,
    stt,
    tts,
    utils,
)
from livekit.agents.language import LanguageCode
from livekit.agents.types import NOT_GIVEN, NotGivenOr

from app.providers.base import (
    AudioChunk,
    AudioFormat,
    FinalTranscript,
    LLMProvider,
    LLMRequest,
    ProviderError,
    SpeechBoundary,
    StreamEnd,
    STTInput,
    STTProvider,
    TextDelta,
    TTSProvider,
    TTSRequest,
)

# Sağlayıcı hatasını LiveKit'in tekrar deneme mantığının anladığı hataya çevirir.
# LiveKit ilk parça gönderildikten sonra asla tekrar denemez (kullanıcı aynı şeyi iki kez duymaz).


def _to_livekit_error(exc: ProviderError) -> APIConnectionError:
    return APIConnectionError(str(exc), retryable=exc.retryable)


# --- STT ------------------------------------------------------------------------


class EvaSTT(stt.STT[Never]):
    """Bizim ``STTProvider``'ımızı LiveKit'e takar. ``mark_speech_end`` çağrılınca (VAD
    "kullanıcı sustu" deyince) açık akışa ``SpeechBoundary`` konur."""

    def __init__(self, provider: STTProvider, *, language: str = "tr") -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=True, interim_results=True, offline_recognize=False
            )
        )
        self._provider = provider
        self._language = language
        self._streams: set[EvaSTTStream] = set()

    @property
    def model(self) -> str:
        return self._provider.name

    @property
    def provider(self) -> str:
        return self._provider.name

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        raise NotImplementedError("only streaming recognition is supported")

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "EvaSTTStream":
        stream = EvaSTTStream(self, conn_options=conn_options)
        self._streams.add(stream)
        return stream

    def mark_speech_end(self) -> None:
        for stream in list(self._streams):
            stream.mark_speech_end()

    def _forget(self, stream: "EvaSTTStream") -> None:
        self._streams.discard(stream)


class EvaSTTStream(stt.RecognizeStream):
    def __init__(self, owner: EvaSTT, *, conn_options: APIConnectOptions) -> None:
        fmt = owner._provider.input_format
        # sample_rate verince LiveKit odadaki sesi sağlayıcının istediği hıza kendisi çevirir.
        super().__init__(stt=owner, conn_options=conn_options, sample_rate=fmt.sample_rate)
        self._owner = owner
        self._format = fmt
        self._boundaries: asyncio.Queue[None] = asyncio.Queue()

    def mark_speech_end(self) -> None:
        self._boundaries.put_nowait(None)

    async def _audio(self) -> AsyncIterator[STTInput]:
        """LiveKit ses karelerini + "sustu" işaretlerini tek bir sırayla sağlayıcıya verir."""
        frames = self._input_ch.__aiter__()
        next_frame: asyncio.Task[object] | None = None
        next_boundary: asyncio.Task[None] | None = None
        try:
            while True:
                if next_frame is None:
                    next_frame = asyncio.ensure_future(frames.__anext__())
                if next_boundary is None:
                    next_boundary = asyncio.ensure_future(self._boundaries.get())
                done, _ = await asyncio.wait(
                    {next_frame, next_boundary}, return_when=asyncio.FIRST_COMPLETED
                )
                if next_boundary in done:
                    next_boundary = None
                    yield SpeechBoundary()
                if next_frame in done:
                    try:
                        item = next_frame.result()
                    except StopAsyncIteration:
                        return
                    finally:
                        next_frame = None
                    if isinstance(item, self._FlushSentinel):
                        yield SpeechBoundary()
                    else:
                        yield AudioChunk(bytes(item.data), self._format)  # type: ignore[attr-defined]
        finally:
            for task in (next_frame, next_boundary):
                if task is not None:
                    task.cancel()

    async def _run(self) -> None:
        provider = self._owner._provider
        speaking = False
        try:
            async for event in provider.transcribe(self._audio(), language=self._owner._language):
                text = event.text.strip()
                if not text:
                    continue
                if not speaking:
                    speaking = True
                    self._event_ch.send_nowait(
                        stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
                    )
                kind = (
                    stt.SpeechEventType.FINAL_TRANSCRIPT
                    if isinstance(event, FinalTranscript)
                    else stt.SpeechEventType.INTERIM_TRANSCRIPT
                )
                data = stt.SpeechData(language=LanguageCode(self._owner._language), text=text)
                self._event_ch.send_nowait(stt.SpeechEvent(type=kind, alternatives=[data]))
                if isinstance(event, FinalTranscript) and event.end_of_turn:
                    speaking = False
                    self._event_ch.send_nowait(
                        stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
                    )
        except ProviderError as exc:
            raise _to_livekit_error(exc) from exc
        finally:
            self._owner._forget(self)


# --- LLM ------------------------------------------------------------------------

# Kullanıcının son sözünü (LiveKit tur id'si + metin) alıp sağlayıcıya gidecek isteği kurar.
# Ajan bunu veritabanı işlemleriyle doldurur (``CallTurns.prepare_reply``).
PrepareReply = Callable[[str | None, str | None], Awaitable[LLMRequest]]


class EvaLLM(llm.LLM[Never]):
    """LiveKit'in tuttuğu sohbet geçmişini kullanmaz: isteği her turda bizim veritabanımızdan,
    metin sohbetiyle aynı persona/hafıza/geçmiş kurallarıyla kurar (``PrepareReply``)."""

    def __init__(self, provider: LLMProvider, prepare: PrepareReply) -> None:
        super().__init__()
        self._provider = provider
        self._prepare = prepare

    @property
    def model(self) -> str:
        return self._provider.name

    @property
    def provider(self) -> str:
        return self._provider.name

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, object]] = NOT_GIVEN,
    ) -> "EvaLLMStream":
        return EvaLLMStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


def last_user_turn(chat_ctx: llm.ChatContext) -> tuple[str | None, str | None]:
    """Son asistan cevabından sonra gelen kullanıcı sözü: (tur id'si, metin).
    Yoksa (görüşmenin açılışı) ``(None, None)``."""
    for item in reversed(chat_ctx.items):
        if not isinstance(item, llm.ChatMessage):
            continue
        if item.role == "assistant":
            return None, None
        if item.role == "user":
            text = (item.text_content or "").strip()
            return (item.id, text) if text else (None, None)
    return None, None


class EvaLLMStream(llm.LLMStream):
    def __init__(
        self,
        owner: EvaLLM,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(owner, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._owner = owner

    async def _run(self) -> None:
        item_id, text = last_user_turn(self._chat_ctx)
        request = await self._owner._prepare(item_id, text)
        chunk_id = utils.shortuuid("eva_")
        try:
            async for event in self._owner._provider.stream(request):
                if isinstance(event, TextDelta):
                    self._event_ch.send_nowait(
                        llm.ChatChunk(
                            id=chunk_id,
                            delta=llm.ChoiceDelta(role="assistant", content=event.text),
                        )
                    )
                elif isinstance(event, StreamEnd):
                    self._event_ch.send_nowait(
                        llm.ChatChunk(
                            id=chunk_id,
                            usage=llm.CompletionUsage(
                                completion_tokens=event.output_tokens,
                                prompt_tokens=event.input_tokens,
                                prompt_cached_tokens=event.cache_read_tokens,
                                total_tokens=event.input_tokens + event.output_tokens,
                            ),
                        )
                    )
        except ProviderError as exc:
            raise _to_livekit_error(exc) from exc


# --- TTS ------------------------------------------------------------------------


class EvaTTS(tts.TTS[Never]):
    def __init__(
        self, provider: TTSProvider, *, voice_id: str, language: str = "tr", sample_rate: int
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=True),
            sample_rate=sample_rate,
            num_channels=1,
        )
        self._provider = provider
        self._request = TTSRequest(
            voice_id=voice_id, language=language, output=AudioFormat(sample_rate=sample_rate)
        )

    @property
    def model(self) -> str:
        return self._provider.name

    @property
    def provider(self) -> str:
        return self._provider.name

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> "EvaChunkedStream":
        return EvaChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> "EvaSynthesizeStream":
        return EvaSynthesizeStream(tts=self, conn_options=conn_options)

    async def _pump(self, text: AsyncIterator[str], emitter: tts.AudioEmitter) -> None:
        emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=self.sample_rate,
            num_channels=1,
            mime_type="audio/pcm",
            stream=True,
        )
        emitter.start_segment(segment_id=uuid.uuid4().hex)
        try:
            async for chunk in self._provider.synthesize(text, self._request):
                emitter.push(chunk.data)
        except ProviderError as exc:
            raise _to_livekit_error(exc) from exc
        emitter.end_input()


class EvaChunkedStream(tts.ChunkedStream):
    """Tek parça metin (ör. ``session.say``) için."""

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        async def one() -> AsyncIterator[str]:
            yield self._input_text

        owner = self._tts
        if not isinstance(owner, EvaTTS):  # pragma: no cover - her zaman EvaTTS
            raise APIStatusError("unexpected tts owner", retryable=False)
        await owner._pump(one(), output_emitter)


class EvaSynthesizeStream(tts.SynthesizeStream):
    """LLM'den akan metni geldikçe sese çevirir (ilk cümle hazır olunca ses başlar, §4.3)."""

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        async def text() -> AsyncIterator[str]:
            async for item in self._input_ch:
                if isinstance(item, str):
                    yield item

        owner = self._tts
        if not isinstance(owner, EvaTTS):  # pragma: no cover - her zaman EvaTTS
            raise APIStatusError("unexpected tts owner", retryable=False)
        await owner._pump(text(), output_emitter)
