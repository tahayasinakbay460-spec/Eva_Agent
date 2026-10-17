"""LemonSlice yalnızca-yüz adaptörü: sahte HTTP API'siyle, ağsız."""

import json
from email.parser import BytesParser
from email.policy import default
from typing import Any

import httpx
import pytest

from app.providers.base import (
    AvatarSessionRequest,
    EnrollmentSample,
    MediaRoom,
    ProviderError,
)
from app.providers.lemonslice import LemonSliceAvatarEnrollmentProvider, LemonSliceProvider
from app.providers.registry import create_adapter, registered_adapters

ROOM = MediaRoom(url="wss://eva.livekit.cloud", token="avatar-jwt", session_id="RM_abc")
REQUEST = AvatarSessionRequest(
    avatar_id="agent-1", room_name="eva-room", max_duration_s=600, idle_timeout_s=60, room=ROOM
)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEMONSLICE_API_KEY", "ls-key")


class FakeApi:
    def __init__(self, status: int = 201, body: Any = None, control_status: int = 200) -> None:
        self.status = status
        self.body = {"session_id": "s-1", "control_url": "x"} if body is None else body
        self.control_status = control_status
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.images: list[tuple[str, str, bytes]] = []  # (dosya adı, tür, içerik)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            body = self._multipart(content_type, request.content)
        else:
            body = json.loads(request.content)
        self.calls.append((request.url.path, body, dict(request.headers)))
        if request.url.path.endswith("/control"):
            return httpx.Response(self.control_status, json={"success": True})
        return httpx.Response(self.status, json=self.body)

    def _multipart(self, content_type: str, content: bytes) -> dict[str, Any]:
        raw = f"Content-Type: {content_type}\r\n\r\n".encode() + content
        message = BytesParser(policy=default).parsebytes(raw)
        body: dict[str, Any] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            data = part.get_payload(decode=True)
            assert isinstance(data, bytes)
            if name == "payload":
                assert part.get_content_type() == "application/json"
                body = json.loads(data)
            elif name == "image":
                self.images.append((part.get_filename() or "", part.get_content_type(), data))
        return body


def provider(api: FakeApi, **options: Any) -> LemonSliceProvider:
    return LemonSliceProvider(transport=httpx.MockTransport(api), **options)


async def test_starts_avatar_in_our_room() -> None:
    api = FakeApi()
    session = await provider(api).start_session(REQUEST)

    assert session.session_id == "s-1"
    assert session.audio_via_room is True
    assert session.input_format.sample_rate == 16_000
    assert session.reports_playback
    [(path, body, headers)] = api.calls
    assert path == "/api/liveai/sessions"
    assert headers["x-api-key"] == "ls-key"
    assert body == {
        "transport_type": "livekit",
        "properties": {
            "livekit_url": "wss://eva.livekit.cloud",
            "livekit_token": "avatar-jwt",
            "livekit_session_id": "RM_abc",
        },
        "agent_id": "agent-1",
        # Boşta geçen süre de ücretli: bizim boşta kalma sınırımız gider.
        "idle_timeout": 60,
    }


async def test_image_url_and_options() -> None:
    api = FakeApi()
    request = AvatarSessionRequest(
        avatar_id="https://cdn.example.com/eva.png",
        room_name="r",
        max_duration_s=60,
        idle_timeout_s=30,
        room=ROOM,
    )
    await provider(api, model="cwm-1-lite", aspect_ratio="9x16").start_session(request)
    body = api.calls[0][1]
    assert body["agent_image_url"] == "https://cdn.example.com/eva.png"
    assert "agent_id" not in body
    assert body["model"] == "cwm-1-lite" and body["aspect_ratio"] == "9x16"


async def test_close_terminates_once() -> None:
    api = FakeApi()
    session = await provider(api).start_session(REQUEST)
    await session.close()
    await session.close()
    assert [(c[0], c[1]) for c in api.calls[1:]] == [
        ("/api/liveai/sessions/s-1/control", {"event": "terminate"})
    ]


async def test_close_of_already_ended_session_is_fine() -> None:
    api = FakeApi(control_status=404)
    session = await provider(api).start_session(REQUEST)
    await session.close()
    assert session.closed


async def test_missing_key_fails_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEMONSLICE_API_KEY")
    api = FakeApi()
    with pytest.raises(ProviderError) as err:
        await provider(api).start_session(REQUEST)
    assert not err.value.retryable and api.calls == []


@pytest.mark.parametrize(
    "room",
    [
        None,
        MediaRoom(url="wss://eva.livekit.cloud", token="t"),  # oda oturum kimliği yok
        MediaRoom(url="ws://localhost:7880", token="t", session_id="RM_1"),
    ],
)
async def test_bad_room_is_refused_without_calling(room: MediaRoom | None) -> None:
    api = FakeApi()
    request = AvatarSessionRequest(
        avatar_id="a", room_name="r", max_duration_s=60, idle_timeout_s=30, room=room
    )
    with pytest.raises(ProviderError) as err:
        await provider(api).start_session(request)
    assert not err.value.retryable and api.calls == []


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(400, False), (401, False), (402, False), (403, False), (404, False), (500, True)],
)
async def test_http_errors(status: int, retryable: bool) -> None:
    with pytest.raises(ProviderError) as err:
        await provider(FakeApi(status, {"detail": "nope"})).start_session(REQUEST)
    assert err.value.retryable is retryable
    assert "nope" in str(err.value)


async def test_response_without_session_id_is_an_error() -> None:
    with pytest.raises(ProviderError):
        await provider(FakeApi(body={"control_url": "x"})).start_session(REQUEST)


async def test_connection_error_is_retryable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ProviderError) as err:
        await LemonSliceProvider(transport=httpx.MockTransport(boom)).start_session(REQUEST)
    assert err.value.retryable


def test_registered_as_network_adapter() -> None:
    assert "lemonslice" in registered_adapters("avatar")
    assert "lemonslice" not in registered_adapters("avatar", offline_only=True)
    adapter = create_adapter("avatar", "lemonslice", model="cwm-1")
    assert isinstance(adapter, LemonSliceProvider)


PHOTO = EnrollmentSample(b"\x89PNG\r\n\x1a\nface", "image/png")
WEBM = EnrollmentSample(b"\x1a\x45\xdf\xa3", "video/webm")


async def test_uploads_the_users_own_photo_for_this_session() -> None:
    api = FakeApi()
    request = AvatarSessionRequest(
        avatar_id="eva-enrollment-1",
        room_name="r",
        max_duration_s=60,
        idle_timeout_s=30,
        room=ROOM,
        image=PHOTO,
    )
    session = await provider(api).start_session(request)

    assert session.session_id == "s-1"
    [(path, body, headers)] = api.calls
    assert path == "/api/liveai/sessions" and headers["x-api-key"] == "ls-key"
    # Fotoğraf multipart ile gider; herkese açık adres ya da LemonSlice'ta kayıtlı avatar yok.
    assert api.images == [("image.png", "image/png", PHOTO.data)]
    assert "agent_id" not in body and "agent_image_url" not in body
    assert body["properties"]["livekit_session_id"] == "RM_abc"
    assert body["idle_timeout"] == 30


async def test_non_image_sample_is_refused_without_calling() -> None:
    api = FakeApi()
    request = AvatarSessionRequest(
        avatar_id="x", room_name="r", max_duration_s=60, idle_timeout_s=30, room=ROOM, image=WEBM
    )
    with pytest.raises(ProviderError) as err:
        await provider(api).start_session(request)
    assert not err.value.retryable and api.calls == []


def test_says_it_works_from_a_photo() -> None:
    assert LemonSliceProvider.accepts_image is True


async def test_enrollment_needs_a_photo_and_sends_nothing() -> None:
    enrollment = LemonSliceAvatarEnrollmentProvider()
    with pytest.raises(ProviderError) as err:
        await enrollment.create_avatar([WEBM], label="eva-1")
    assert not err.value.retryable
    ref = await enrollment.create_avatar([WEBM, PHOTO], label="eva-1")
    assert (ref.provider, ref.asset_id) == ("lemonslice", "eva-1")
    await enrollment.delete_avatar(ref.asset_id)  # sağlayıcıda silinecek bir şey yok


def test_enrollment_registered_as_offline_adapter() -> None:
    assert "lemonslice" in registered_adapters("avatar_enrollment", offline_only=True)
    adapter = create_adapter("avatar_enrollment", "lemonslice")
    assert isinstance(adapter, LemonSliceAvatarEnrollmentProvider)
