"""``AvatarProvider`` için Anam adaptörü — yalnızca yüz (avatar-only) modu (CLAUDE.md §4.2).

Konuşmayı (STT → LLM → TTS) biz yaparız; Anam yalnızca verdiğimiz sese göre dudak senkronlu
yüz videosunu üretir. LiveAvatar'dan farkı: Anam **bizim** LiveKit odamıza katılır ve sesi
odanın standart avatar kanalından (LiveKit data stream) kendisi alır. Bu yüzden oturum
``RoomAvatarSession``'dır; sesi gerçek zamanlı katman yollar.

Güncel dokümana ve resmî LiveKit eklentisine göre (2026-10-17; anam.ai/docs,
livekit-plugins-anam 1.8.8):

1. ``POST /v1/engine/session`` (``Authorization: Bearer <API anahtarı>``):
   ``personaConfig`` = avatar + ``llmId=CUSTOMER_CLIENT_V1`` (LLM bizde) + en uzun süre;
   ``environment`` = bizim oda adresimiz + avatar için ürettiğimiz token. Cevap: ``sessionId``.
2. Ses 24 kHz PCM, odanın data stream kanalıyla; Anam ilk kareden önce ~800 ms ses ister.
3. Oturum, avatar odadan çıkınca biter. LiveKit oturumlarında ``/v1/sessions/{id}/stop``
   çalışmaz (404); oda kapanınca (``delete_room_on_close``) avatar da çıkar. Ajan çökse bile
   ``maxSessionLengthSeconds`` oturumu Anam tarafında keser.
4. Oda adresi internetten erişilebilir olmalı: localhost / özel ağ adresleri 400 ile reddedilir.
   Bunu istek atmadan yakalarız (boşuna çağrı ve anlaşılmaz hata olmasın).

Anahtar ``ANAM_API_KEY`` ortam değişkeninden okunur; asla loglanmaz, istemciye gitmez.
"""

import ipaddress
import os
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from app.providers.base import AudioFormat, AvatarSessionRequest, ProviderError

DEFAULT_API = "https://api.anam.ai"
PCM_24K = AudioFormat(sample_rate=24_000)
# Anam'ın kendi LLM'i yerine bizim LLM'imiz (resmî eklentiyle aynı değer).
CLIENT_LLM = "CUSTOMER_CLIENT_V1"


def _api_key() -> str:
    key = os.environ.get("ANAM_API_KEY")
    if not key:
        raise ProviderError("ANAM_API_KEY is not set", retryable=False)
    return key


def is_public_url(url: str) -> bool:
    """Anam'ın erişebileceği bir adres mi? (localhost, tek kelimelik ad, özel IP değil)"""
    host = urlsplit(url).hostname
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." in host and host != "localhost" and not host.endswith(".localhost")
    return ip.is_global


class AnamProvider:
    name = "anam"

    def __init__(
        self,
        *,
        api_base: str = DEFAULT_API,
        avatar_model: str = "cara-4",
        region: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_base = api_base
        self._avatar_model = avatar_model
        # "eu" | "us"; boşsa Anam seçer. Bölge seçimi her planda açık olmayabilir (403).
        self._region = region
        self._transport = transport

    async def start_session(self, request: AvatarSessionRequest) -> "AnamSession":
        if request.room is None:
            raise ProviderError("anam needs our media room", retryable=False)
        if not is_public_url(request.room.url):
            raise ProviderError(
                "anam needs a publicly reachable livekit url (not localhost)", retryable=False
            )
        persona: dict[str, Any] = {
            "type": "ephemeral",
            "name": "EVA",
            "avatarId": request.avatar_id,
            "llmId": CLIENT_LLM,
            "maxSessionLengthSeconds": request.max_duration_s,
        }
        if self._avatar_model:
            persona["avatarModel"] = self._avatar_model
        body: dict[str, Any] = {
            "personaConfig": persona,
            "environment": {"livekitUrl": request.room.url, "livekitToken": request.room.token},
        }
        if self._region:
            body["sessionOptions"] = {"region": self._region}
        data = await self._post("/v1/engine/session", body)
        session_id = data.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ProviderError("anam returned no session id", retryable=False)
        return AnamSession(session_id)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {_api_key()}"}
        try:
            async with httpx.AsyncClient(
                base_url=self._api_base, headers=headers, timeout=15.0, transport=self._transport
            ) as client:
                r = await client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise ProviderError("anam connection error", retryable=True) from exc
        if r.status_code >= 400:
            # 402: ödeme / ücretsiz dakika bitti · 429: eşzamanlı oturum ya da harcama sınırı.
            # Bunlarda hemen yeniden denemek boşuna; yalnızca 5xx yeniden denenebilir.
            raise ProviderError(
                f"anam {path} failed: {r.status_code}{_error_reason(r)}",
                retryable=r.status_code >= 500,
            )
        data = r.json()
        if not isinstance(data, dict):
            raise ProviderError(f"anam {path} returned unexpected body", retryable=False)
        return data


def _error_reason(r: httpx.Response) -> str:
    """Anam'ın hata kodu ve kısa açıklaması. Gövdenin tamamı alınmaz: doğrulama hataları
    gönderdiğimiz değerleri (ör. oda token'ı) geri yansıtabilir, bunlar loglanmamalı."""
    try:
        data = r.json()
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    parts = [
        str(data[k])[:120] for k in ("code", "error", "message") if isinstance(data.get(k), str)
    ]
    return f" ({'; '.join(parts)})" if parts else ""


class AnamSession:
    audio_via_room: Literal[True] = True
    input_format = PCM_24K
    reports_playback = False

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.closed = False

    async def close(self) -> None:
        # Kapatacak bir çağrı yok (bkz. modül notu 3): avatar oda kapanınca çıkar.
        self.closed = True
