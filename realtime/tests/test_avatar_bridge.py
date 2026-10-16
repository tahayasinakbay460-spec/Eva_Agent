"""Görüntülü görüşme köprüsü: EVA'nın sesi avatara gider, avatarın konuşma olayları LiveKit'e
döner; söz kesilince avatar susar ve "kesildi" bildirilir."""

import asyncio
from typing import Any

import jwt
from livekit import rtc
from livekit.agents.voice.io import AudioOutput

from app.core.config import Settings
from app.providers.mock import MockAvatarSession
from eva_realtime.avatar import AVATAR_IDENTITY, AvatarBridge, mint_avatar_token


def _frame(ms: int = 100, rate: int = 24_000) -> rtc.AudioFrame:
    samples = rate * ms // 1000
    return rtc.AudioFrame(b"\x01\x00" * samples, rate, 1, samples)


async def _bridge() -> tuple[AvatarBridge, MockAvatarSession, list[Any]]:
    avatar = MockAvatarSession("s1")
    bridge = AvatarBridge(avatar)
    attached: list[AudioOutput] = []
    await bridge.attach(attached.append)
    assert attached == [bridge.audio_output], "agent audio now flows into the bridge"
    finished: list[Any] = []
    bridge.audio_output.on("playback_finished", finished.append)
    return bridge, avatar, finished


async def _until(condition: Any) -> None:
    """Arka plandaki köprü görevleri işini bitirene kadar (en fazla 2 sn) bekler."""
    async with asyncio.timeout(2.0):
        for _ in range(200):
            if condition():
                return
            await asyncio.sleep(0.01)
    raise AssertionError("condition never became true")


async def test_speech_goes_to_the_avatar_and_completion_is_reported() -> None:
    bridge, avatar, finished = await _bridge()
    for _ in range(3):
        await bridge.audio_output.capture_frame(_frame())
    bridge.audio_output.flush()  # söz bitti
    await _until(lambda: finished)
    assert avatar.audio_bytes == 3 * 2400 * 2
    assert finished[0].interrupted is False
    assert abs(finished[0].playback_position - 0.3) < 0.01
    await bridge.aclose()
    assert avatar.closed


async def test_barge_in_interrupts_the_avatar() -> None:
    bridge, avatar, finished = await _bridge()
    await bridge.audio_output.capture_frame(_frame())
    await _until(lambda: avatar.audio_bytes > 0)
    bridge.audio_output.clear_buffer()  # kullanıcı söze girdi
    await _until(lambda: finished)
    assert avatar.interrupts == 1
    assert finished[0].interrupted is True
    await bridge.aclose()


async def test_other_sample_rates_are_resampled_to_the_avatars() -> None:
    bridge, avatar, finished = await _bridge()
    for _ in range(5):
        await bridge.audio_output.capture_frame(_frame(rate=48_000))
    bridge.audio_output.flush()
    await _until(lambda: finished)
    assert avatar.audio_bytes > 0
    await bridge.aclose()


def test_avatar_token_acts_on_behalf_of_the_agent() -> None:
    secret = "s" * 32
    settings = Settings(
        _env_file=None, livekit_url="ws://x", livekit_api_key="k", livekit_api_secret=secret
    )
    token = mint_avatar_token(settings, room_name="eva-room", agent_identity="agent-1")
    claims = jwt.decode(token, secret, algorithms=["HS256"])
    assert claims["sub"] == AVATAR_IDENTITY
    assert claims["kind"] == "agent"
    assert claims["attributes"] == {"lk.publish_on_behalf": "agent-1"}
    assert claims["video"]["room"] == "eva-room" and claims["video"]["roomJoin"]
    assert claims["exp"] - claims["nbf"] <= 300
