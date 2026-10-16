"""ElevenLabs adaptörleri: akışlı metinden sese (TTS) ve rızalı ses klonu (§4.2).

Güncel dokümana göre yazıldı (2026-10-16; elevenlabs.io/docs):

- TTS: ``wss://.../v1/text-to-speech/{voice_id}/stream-input`` WebSocket'i. İlk mesaj tek
  boşluk + ses ayarları; sonra metin parçaları; boş metin ("") bağlantıyı kapatır ve kalanı
  seslendirir. Cevap ``{"audio": base64, "isFinal": ...}`` mesajlarıyla gelir.
  Her cevap turu için yeni bağlantı açılır; söz kesmede (barge-in) bağlantı kapatılır, böylece
  ElevenLabs boşuna karakter seslendirmez. (Görüşme boyu tek bağlantı = multi-stream-input,
  gecikme ölçümüne göre sonraki adım.)
- Ses klonu: ``POST /v1/voices/add`` (multipart, ``files`` tekrar eder). API'de rıza alanı
  yok; bu çağrı yalnızca bizim rıza + inceleme akışımız onayladıktan sonra yapılır (§11.3).
- Silme: ``DELETE /v1/voices/{id}``; "zaten yok" cevapları başarı sayılır (idempotent).

Anahtar ``ELEVENLABS_API_KEY`` ortam değişkeninden okunur; asla loglanmaz.
"""

import asyncio
import base64
import contextlib
import json
import os
from collections.abc import AsyncIterable, AsyncIterator, Callable, Sequence
from typing import Any

import httpx
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import WebSocketException

from app.providers.base import (
    AudioChunk,
    EnrollmentSample,
    ProviderAssetRef,
    ProviderError,
    TTSRequest,
)

DEFAULT_HTTP = "https://api.elevenlabs.io"
DEFAULT_WS = "wss://api.elevenlabs.io"
# "Zaten silinmiş / hiç yok" anlamına gelen hata kodları (eski ve yeni biçimler).
_GONE_CODES = ("voice_not_found", "invalid_voice_id", "voice_does_not_exist")
_RETRYABLE_STATUS = frozenset({409, 429, 500, 502, 503, 504})


def _api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise ProviderError("ELEVENLABS_API_KEY is not set", retryable=False)
    return key


class ElevenLabsTTSProvider:
    name = "elevenlabs"

    def __init__(
        self,
        *,
        model_id: str = "eleven_flash_v2_5",
        ws_base: str = DEFAULT_WS,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        speed: float = 1.0,
        connect: Callable[..., Any] = ws_connect,
    ) -> None:
        self._model_id = model_id
        self._ws_base = ws_base
        self._voice_settings = {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "speed": speed,
        }
        self._connect = connect

    async def synthesize(
        self, text: AsyncIterable[str], request: TTSRequest
    ) -> AsyncIterator[AudioChunk]:
        fmt = request.output
        if fmt.channels != 1:
            raise ProviderError("elevenlabs pcm output is mono", retryable=False)
        url = (
            f"{self._ws_base}/v1/text-to-speech/{request.voice_id}/stream-input"
            f"?model_id={self._model_id}&output_format=pcm_{fmt.sample_rate}"
            f"&language_code={request.language}&inactivity_timeout=60"
        )
        try:
            async with self._connect(url, additional_headers={"xi-api-key": _api_key()}) as ws:
                await ws.send(json.dumps({"text": " ", "voice_settings": self._voice_settings}))
                sender = asyncio.create_task(_send_text(ws, text))
                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if message.get("error") or (
                            "message" in message and "audio" not in message
                        ):
                            raise ProviderError("tts stream error", retryable=False)
                        audio = message.get("audio")
                        if audio:
                            yield AudioChunk(base64.b64decode(audio), fmt)
                        if message.get("isFinal"):
                            break
                    if sender.done() and sender.exception() is not None:
                        raise ProviderError("tts text feed failed", retryable=False)
                finally:
                    # Söz kesildiyse (görev iptal) metin göndermeyi de durdur.
                    sender.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await sender
        except (OSError, WebSocketException) as exc:
            raise ProviderError("tts connection error", retryable=True) from exc


async def _send_text(ws: Any, text: AsyncIterable[str]) -> None:
    async for fragment in text:
        if fragment.strip():
            # Parçalar boşlukla bitmeli; ElevenLabs kelimeleri böyle ayırır.
            chunk = fragment if fragment.endswith(" ") else fragment + " "
            await ws.send(json.dumps({"text": chunk}))
    await ws.send(json.dumps({"text": ""}))  # kapat: kalan metni seslendir ve bitir


class ElevenLabsVoiceEnrollmentProvider:
    name = "elevenlabs"

    def __init__(
        self,
        *,
        http_base: str = DEFAULT_HTTP,
        remove_background_noise: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._http_base = http_base
        self._remove_noise = remove_background_noise
        self._transport = transport
        self._timeout_s = timeout_s

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._http_base,
            headers={"xi-api-key": _api_key()},
            timeout=self._timeout_s,
            transport=self._transport,
        )

    async def create_voice(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef:
        if not samples:
            raise ValueError("at least one sample is required")
        files = [
            ("files", (f"sample_{i}{_extension(s.media_type)}", s.data, s.media_type))
            for i, s in enumerate(samples)
        ]
        data = {
            "name": label,
            "remove_background_noise": "true" if self._remove_noise else "false",
            "description": "EVA: consented voice clone",
        }
        try:
            async with self._client() as client:
                r = await client.post("/v1/voices/add", data=data, files=files)
        except httpx.HTTPError as exc:
            raise ProviderError("voice clone connection error", retryable=True) from exc
        if r.status_code != 200:
            raise ProviderError(
                f"voice clone failed: {r.status_code} {_error_code(r)}",
                retryable=r.status_code in _RETRYABLE_STATUS,
            )
        body = r.json()
        voice_id = body.get("voice_id")
        if not isinstance(voice_id, str) or not voice_id:
            raise ProviderError("voice clone returned no id", retryable=False)
        if body.get("requires_verification"):
            # Doğrulama bekleyen ses kullanılamaz; yarım klon bırakmamak için hemen sil.
            await self.delete_voice(voice_id)
            raise ProviderError("voice requires provider verification", retryable=False)
        return ProviderAssetRef(provider=self.name, asset_id=voice_id)

    async def delete_voice(self, asset_id: str) -> None:
        try:
            async with self._client() as client:
                r = await client.delete(f"/v1/voices/{asset_id}")
        except httpx.HTTPError as exc:
            raise ProviderError("voice delete connection error", retryable=True) from exc
        if r.status_code == 200 or r.status_code == 404:
            return
        if r.status_code in (400, 422) and any(c in r.text for c in _GONE_CODES):
            return
        raise ProviderError(
            f"voice delete failed: {r.status_code} {_error_code(r)}",
            retryable=r.status_code in _RETRYABLE_STATUS,
        )


def _error_code(response: httpx.Response) -> str:
    """Hata gövdesinden yalnızca kodu alır (mesajlar loglara girmesin diye)."""
    try:
        body = response.json()
    except ValueError:
        return ""
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("code") or detail.get("status") or "")
    return ""


def _extension(media_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
    }.get(media_type, "")
