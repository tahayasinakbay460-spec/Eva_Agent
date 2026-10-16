"""LiveKit köprüsü: gerçek LiveKit sınıfları + bizim sahte (mock) sağlayıcılarımız, ağsız."""

import asyncio
import json
import uuid
from typing import Any

import pytest
from livekit import rtc
from livekit.agents import llm, stt

from app.providers.base import LLMMessage, LLMRequest, SystemBlock
from app.providers.mock import MOCK_HEARD_TEXT, MockLLMProvider, MockSTTProvider, MockTTSProvider
from eva_realtime.adapters import EvaLLM, EvaSTT, EvaTTS, last_user_turn
from eva_realtime.agent import parse_call_id, timings_from


def _frame(sample_rate: int = 24_000, ms: int = 20) -> rtc.AudioFrame:
    samples = sample_rate * ms // 1000
    # UTF-8 olmayan baytlar: sahte STT bunu "gerçek ses" sayar.
    data = (bytes(range(128, 256)) * (samples * 2 // 128 + 1))[: samples * 2]
    return rtc.AudioFrame(data, sample_rate, 1, samples)


async def test_stt_speech_end_closes_the_segment() -> None:
    eva_stt = EvaSTT(MockSTTProvider())
    stream = eva_stt.stream()
    for _ in range(10):
        stream.push_frame(_frame())
    await asyncio.sleep(0.05)
    eva_stt.mark_speech_end()  # VAD "kullanıcı sustu" dedi

    events: list[stt.SpeechEvent] = []

    async def collect() -> None:
        async for ev in stream:
            events.append(ev)
            if ev.type == stt.SpeechEventType.END_OF_SPEECH:
                return

    await asyncio.wait_for(collect(), timeout=5)
    await stream.aclose()
    kinds = [e.type for e in events]
    assert kinds[0] == stt.SpeechEventType.START_OF_SPEECH
    assert stt.SpeechEventType.FINAL_TRANSCRIPT in kinds
    final = next(e for e in events if e.type == stt.SpeechEventType.FINAL_TRANSCRIPT)
    assert final.alternatives[0].text == MOCK_HEARD_TEXT
    assert final.alternatives[0].language == "tr"


def _ctx(*turns: tuple[str, str]) -> llm.ChatContext:
    ctx = llm.ChatContext.empty()
    for role, text in turns:
        ctx.add_message(role=role, content=text)  # type: ignore[arg-type]
    return ctx


def test_last_user_turn() -> None:
    ctx = _ctx(("assistant", "Selam!"), ("user", "Nasılsın?"))
    item_id, text = last_user_turn(ctx)
    assert text == "Nasılsın?" and item_id is not None
    assert last_user_turn(_ctx()) == (None, None), "call opening"
    assert last_user_turn(_ctx(("user", "a"), ("assistant", "b"))) == (None, None)


async def test_llm_builds_the_request_from_our_side_and_streams_text() -> None:
    calls: list[tuple[str | None, str | None]] = []

    async def prepare(item_id: str | None, text: str | None) -> LLMRequest:
        calls.append((item_id, text))
        return LLMRequest(
            model="m",
            system=(SystemBlock("kurallar", cacheable=True),),
            messages=(LLMMessage("user", text or "açılış"),),
        )

    eva_llm = EvaLLM(MockLLMProvider(reply="Merhaba, buradayım."), prepare)
    ctx = _ctx(("user", "Selam EVA"))
    text = ""
    async with eva_llm.chat(chat_ctx=ctx) as stream:
        async for chunk in stream:
            if chunk.delta and chunk.delta.content:
                text += chunk.delta.content
    assert text == "Merhaba, buradayım."
    assert calls == [(ctx.items[-1].id, "Selam EVA")]


async def test_tts_streams_audio_frames() -> None:
    eva_tts = EvaTTS(MockTTSProvider(), voice_id="eva-mock", sample_rate=24_000)
    stream = eva_tts.stream()
    stream.push_text("Merhaba ")
    stream.push_text("nasılsın?")
    stream.flush()
    stream.end_input()
    frames: list[rtc.AudioFrame] = []

    async def collect() -> None:
        async for ev in stream:
            frames.append(ev.frame)

    await asyncio.wait_for(collect(), timeout=5)
    await stream.aclose()
    assert frames
    assert all(f.sample_rate == 24_000 and f.num_channels == 1 for f in frames)
    assert sum(f.samples_per_channel for f in frames) > 0


def test_parse_call_id() -> None:
    call_id = uuid.uuid4()
    assert parse_call_id(json.dumps({"call_id": str(call_id)})) == call_id
    with pytest.raises((KeyError, ValueError)):
        parse_call_id("{}")


def test_timings_are_converted_to_milliseconds() -> None:
    user: dict[str, Any] = {"end_of_turn_delay": 0.21, "transcription_delay": 0.15}
    reply: dict[str, Any] = {"llm_node_ttft": 0.3, "tts_node_ttfb": 0.12, "e2e_latency": 0.65}
    timings = timings_from(user, reply)
    assert timings.end_of_turn_ms == 210.0
    assert timings.stt_final_ms == 150.0
    assert timings.llm_ttft_ms == 300.0
    assert timings.tts_ttfb_ms == 120.0
    assert timings.e2e_ms == 650.0
    assert timings_from({}, {}).e2e_ms is None
