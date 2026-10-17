"""Anam avatar-only adaptörü: sahte HTTP API'siyle, ağsız."""

import json
from typing import Any

import httpx
import pytest

from app.providers.anam import AnamProvider, is_public_url
from app.providers.base import AvatarSessionRequest, MediaRoom, ProviderError
from app.providers.registry import create_adapter, registered_adapters

REQUEST = AvatarSessionRequest(
    avatar_id="avatar-1",
    room_name="eva-room",
    max_duration_s=600,
    idle_timeout_s=60,
    room=MediaRoom(url="wss://eva.livekit.cloud", token="avatar-jwt"),
)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANAM_API_KEY", "anam-key")


class FakeApi:
    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status = status
        self.body = {"sessionId": "s-1"} if body is None else body
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            (request.url.path, json.loads(request.content or b"{}"), dict(request.headers))
        )
        return httpx.Response(self.status, json=self.body)


def provider(api: FakeApi, **options: Any) -> AnamProvider:
    return AnamProvider(transport=httpx.MockTransport(api), **options)


async def test_starts_avatar_only_session_in_our_room() -> None:
    api = FakeApi()
    session = await provider(api).start_session(REQUEST)

    assert session.session_id == "s-1"
    assert session.audio_via_room is True
    assert session.input_format.sample_rate == 24_000
    [(path, body, headers)] = api.calls
    assert path == "/v1/engine/session"
    assert headers["authorization"] == "Bearer anam-key"
    assert body == {
        "personaConfig": {
            "type": "ephemeral",
            "name": "EVA",
            "avatarId": "avatar-1",
            # LLM bizde; Anam yalnızca yüzü üretir.
            "llmId": "CUSTOMER_CLIENT_V1",
            # Ajan çökse bile oturum Anam tarafında kesilsin (boşa ücret olmasın).
            "maxSessionLengthSeconds": 600,
            "avatarModel": "cara-4",
        },
        "environment": {"livekitUrl": "wss://eva.livekit.cloud", "livekitToken": "avatar-jwt"},
    }


async def test_region_is_sent_only_when_configured() -> None:
    api = FakeApi()
    await provider(api, region="eu").start_session(REQUEST)
    assert api.calls[0][1]["sessionOptions"] == {"region": "eu"}


async def test_close_is_idempotent_and_makes_no_call() -> None:
    api = FakeApi()
    session = await provider(api).start_session(REQUEST)
    await session.close()
    await session.close()
    assert session.closed and len(api.calls) == 1


async def test_missing_key_fails_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANAM_API_KEY")
    api = FakeApi()
    with pytest.raises(ProviderError) as err:
        await provider(api).start_session(REQUEST)
    assert not err.value.retryable and api.calls == []


@pytest.mark.parametrize(
    "url", ["ws://localhost:7880", "ws://127.0.0.1:7880", "ws://192.168.1.5:7880", "ws://livekit"]
)
async def test_private_room_url_is_refused_without_calling_anam(url: str) -> None:
    api = FakeApi()
    request = AvatarSessionRequest(
        avatar_id="a",
        room_name="r",
        max_duration_s=60,
        idle_timeout_s=30,
        room=MediaRoom(url=url, token="t"),
    )
    with pytest.raises(ProviderError) as err:
        await provider(api).start_session(request)
    assert not err.value.retryable and api.calls == []


async def test_needs_a_room() -> None:
    request = AvatarSessionRequest(
        avatar_id="a", room_name="r", max_duration_s=60, idle_timeout_s=30
    )
    with pytest.raises(ProviderError):
        await provider(FakeApi()).start_session(request)


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(400, False), (401, False), (402, False), (429, False), (503, True)],
)
async def test_http_errors(status: int, retryable: bool) -> None:
    with pytest.raises(ProviderError) as err:
        await provider(FakeApi(status, {"error": "x"})).start_session(REQUEST)
    assert err.value.retryable is retryable


async def test_response_without_session_id_is_an_error() -> None:
    with pytest.raises(ProviderError):
        await provider(FakeApi(body={"engineProtocol": "livekit"})).start_session(REQUEST)


async def test_connection_error_is_retryable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    p = AnamProvider(transport=httpx.MockTransport(boom))
    with pytest.raises(ProviderError) as err:
        await p.start_session(REQUEST)
    assert err.value.retryable


def test_public_url_check() -> None:
    assert is_public_url("wss://eva-abc.livekit.cloud")
    assert is_public_url("https://8.8.8.8")
    for url in (
        "ws://localhost:7880",
        "ws://a.localhost",
        "ws://10.0.0.1",
        "ws://[::1]:7880",
        "nope",
    ):
        assert not is_public_url(url)


def test_registered_as_network_adapter() -> None:
    assert "anam" in registered_adapters("avatar")
    assert "anam" not in registered_adapters("avatar", offline_only=True)
    assert isinstance(create_adapter("avatar", "anam", avatar_model="cara-4"), AnamProvider)
