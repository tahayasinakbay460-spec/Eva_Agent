"""``AvatarProvider`` için LemonSlice adaptörü — yalnızca yüz (CLAUDE.md §4.2).

Konuşmayı (STT → LLM → TTS) biz yaparız; LemonSlice yalnızca verdiğimiz sese göre konuşan
yüz videosunu üretir. Anam gibi **bizim** LiveKit odamıza katılır ve sesi odanın standart
avatar kanalından (LiveKit data stream) kendisi alır; oturum ``RoomAvatarSession``'dır.

Güncel dokümana ve resmî LiveKit eklentisine göre (2026-10-17; lemonslice.com/docs,
livekit-plugins-lemonslice 1.8.8):

1. ``POST /api/liveai/sessions`` (``X-API-Key`` başlığı): ``transport_type=livekit``,
   ``properties`` = oda adresi + avatar token'ı + odanın oturum kimliği (room SID), avatar
   (``agent_id``, ``agent_image_url`` ya da yüklenen görsel) ve ``idle_timeout``. Cevap:
   ``session_id``. Görsel yüklenirken istek multipart olur: ``payload`` (bu JSON) + ``image``.
   Doküman bu ucu doğrudan değil SDK ile çağırmayı öneriyor; biz eklentinin gönderdiği
   gövdenin aynısını gönderiyoruz (sağlayıcı sınırı bizde kalsın diye, §2 kural 4).
2. Ses 16 kHz PCM, data stream ile. Avatar "başladım / bitirdim" bildirimlerini yollar.
3. Ücret: boşta geçen süre de konuşma gibi ücretlendirilir. Görüşme bitince
   ``/{id}/control`` ucuna ``terminate`` gönderilir; oda kapanınca da avatar çıkar.
   Ajan çökerse ``idle_timeout`` (varsayılan 60 sn) oturumu keser; en uzun süre 30 dk.
4. Oda adresi internetten erişilebilir olmalı (Anam'la aynı kontrol).
5. Tek fotoğraftan çalışır (önceden klon/eğitim yok). Kullanıcının yüzü bu yüzden LemonSlice'ta
   saklanmaz: rızalı fotoğraf bizim şifreli depomuzda durur, her görüşmede oradan yüklenir
   (herkese açık adres yok, §11.3). Rıza geri alınınca bir sonraki görüşmede gönderilmez.

Anahtar ``LEMONSLICE_API_KEY`` ortam değişkeninden okunur; asla loglanmaz, istemciye gitmez.
"""

import json
import os
from collections.abc import Sequence
from typing import Any, Literal

import httpx

from app.providers.anam import is_public_url
from app.providers.base import (
    AudioFormat,
    AvatarSessionRequest,
    EnrollmentSample,
    ProviderAssetRef,
    ProviderError,
)

DEFAULT_API = "https://lemonslice.com/api/liveai/sessions"
PCM_16K = AudioFormat(sample_rate=16_000)
IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


def _api_key() -> str:
    key = os.environ.get("LEMONSLICE_API_KEY")
    if not key:
        raise ProviderError("LEMONSLICE_API_KEY is not set", retryable=False)
    return key


class LemonSliceProvider:
    name = "lemonslice"
    accepts_image = True

    def __init__(
        self,
        *,
        api_url: str = DEFAULT_API,
        model: str = "",
        aspect_ratio: str = "",
        agent_prompt: str = "",
        agent_idle_prompt: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        # Boşsa LemonSlice'ın varsayılanı (en iyi model, 2x3 dikey görüntü).
        self._options = {
            k: v
            for k, v in {
                "model": model,
                "aspect_ratio": aspect_ratio,
                "agent_prompt": agent_prompt,
                "agent_idle_prompt": agent_idle_prompt,
            }.items()
            if v
        }
        self._transport = transport

    async def start_session(self, request: AvatarSessionRequest) -> "LemonSliceSession":
        room = request.room
        if room is None or not room.session_id:
            raise ProviderError(
                "lemonslice needs our media room and its session id", retryable=False
            )
        if not is_public_url(room.url):
            raise ProviderError(
                "lemonslice needs a publicly reachable livekit url (not localhost)",
                retryable=False,
            )
        body: dict[str, Any] = {
            "transport_type": "livekit",
            "properties": {
                "livekit_url": room.url,
                "livekit_token": room.token,
                "livekit_session_id": room.session_id,
            },
            # Konuşma yokken ücret işlemesin: bizim boşta kalma sınırımızla aynı.
            "idle_timeout": request.idle_timeout_s,
            **self._options,
        }
        image = request.image
        if image is not None:
            # Kullanıcının kendi fotoğrafı: bizim depomuzdan, yalnızca bu görüşme için.
            if image.media_type not in IMAGE_TYPES:
                raise ProviderError("lemonslice needs a png/jpeg/webp image", retryable=False)
        elif request.avatar_id.startswith("https://"):
            body["agent_image_url"] = request.avatar_id  # herkese açık bir görsel (ör. EVA)
        else:
            body["agent_id"] = request.avatar_id  # LemonSlice'ta oluşturulmuş avatar
        data = await self._post(self._api_url, body, image=image)
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ProviderError("lemonslice returned no session id", retryable=False)
        return LemonSliceSession(self, session_id)

    async def _post(
        self,
        url: str,
        body: dict[str, Any],
        *,
        missing_ok: bool = False,
        image: EnrollmentSample | None = None,
    ) -> dict[str, Any]:
        headers = {"X-API-Key": _api_key()}
        try:
            async with httpx.AsyncClient(
                headers=headers, timeout=60.0, transport=self._transport
            ) as client:
                if image is None:
                    r = await client.post(url, json=body)
                else:
                    ext = image.media_type.split("/", 1)[1]
                    r = await client.post(
                        url,
                        files={
                            "payload": (None, json.dumps(body), "application/json"),
                            "image": (f"image.{ext}", image.data, image.media_type),
                        },
                    )
        except httpx.HTTPError as exc:
            raise ProviderError("lemonslice connection error", retryable=True) from exc
        if missing_ok and r.status_code == 404:
            return {}
        if r.status_code >= 400:
            # 402: bakiye yetersiz · 401/403/404: anahtar ya da avatar yanlış. Yalnızca 5xx
            # yeniden denenebilir.
            raise ProviderError(
                f"lemonslice request failed: {r.status_code}{_error_reason(r)}",
                retryable=r.status_code >= 500,
            )
        data = r.json()
        if not isinstance(data, dict):
            raise ProviderError("lemonslice returned unexpected body", retryable=False)
        return data

    async def terminate(self, session_id: str) -> None:
        # 404 = oturum zaten bitmiş (ör. boşta kalma sınırı doldu): sorun değil.
        await self._post(
            f"{self._api_url}/{session_id}/control", {"event": "terminate"}, missing_ok=True
        )


def _error_reason(r: httpx.Response) -> str:
    """LemonSlice'ın kısa hata açıklaması (``detail``). Uzun gövde alınmaz: gönderdiğimiz
    değerleri (ör. oda token'ı) yansıtabilir, bunlar loglanmamalı."""
    try:
        data = r.json()
    except ValueError:
        return ""
    detail = data.get("detail") if isinstance(data, dict) else None
    return f" ({detail[:120]})" if isinstance(detail, str) else ""


class LemonSliceSession:
    audio_via_room: Literal[True] = True
    input_format = PCM_16K
    reports_playback = True

    def __init__(self, provider: LemonSliceProvider, session_id: str) -> None:
        self._provider = provider
        self.session_id = session_id
        self.closed = False

    async def close(self) -> None:
        # Boşta geçen süre de ücretli: oda kapanmayı beklemeden avatarı hemen durdur.
        if self.closed:
            return
        self.closed = True
        await self._provider.terminate(self.session_id)


class LemonSliceAvatarEnrollmentProvider:
    """LemonSlice için yüz "kaydı": sağlayıcıya hiçbir şey gönderilmez.

    LemonSlice tek fotoğraftan çalıştığı için önceden klon oluşturmaya gerek yok. Onaylanan
    kaydın fotoğrafı bizim depomuzda kalır; burada yalnızca uygun bir fotoğraf olduğu kontrol
    edilir. Silinecek bir şey de yok: ham fotoğrafı imha etmek işçinin işi (§11.3).
    """

    name = "lemonslice"

    async def create_avatar(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef:
        if not samples:
            raise ValueError("at least one sample is required")
        if not any(s.media_type in IMAGE_TYPES for s in samples):
            raise ProviderError("lemonslice needs a face photo sample", retryable=False)
        return ProviderAssetRef(provider=self.name, asset_id=label)

    async def delete_avatar(self, asset_id: str) -> None:
        return None
