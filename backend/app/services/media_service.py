"""EVA'nın sesi ve yüzü: katalogdan seçim ve kullanıcının kendi klonu/fotoğrafı.

Ses ve yüz birbirinden bağımsız seçilir: kullanıcı hazır bir yüzü hazır bir sesle, kendi
fotoğrafını hazır bir sesle ya da kendi klon sesiyle eşleştirebilir. Seçim kullanıcı + persona
başına saklanır; seçilmemişse personanın varsayılanı (EVA'nın kendi sesi ve yüzü) kullanılır.
"Kendi" seçenekleri yalnızca rızası onaylanmış ve aktif bir kayıt varsa açılır; görüşmede rıza
her turda yeniden kontrol edilir (voice_service).
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.media import MediaPreference
from app.models.persona import Persona
from app.models.user import User
from app.persona.media import (
    FILE_PREFIX,
    OWN,
    MediaCatalog,
    MediaKind,
    MediaNotConfiguredError,
    MediaOption,
    load_catalog,
    media_image,
)
from app.providers.base import AudioFormat, EnrollmentSample, TTSRequest
from app.providers.registry import ProviderRegistry
from app.services import biometric_service, persona_service

# Hazır seslerin önizlemesi yalnızca bu sabit cümleyle (maliyet ve kötüye kullanım sınırı).
VOICE_PREVIEW_SENTENCE = {
    "tr": "Merhaba! Seninle bu sesle konuşmaya ne dersin?",
    "en": "Hi! How would you like me to talk to you with this voice?",
}


class MediaChoiceError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class Choice:
    voice: str
    avatar: str


@dataclass(frozen=True, slots=True)
class OptionView:
    key: str
    name: str
    # Yüzün küçük resmi gösterilebilir mi (``GET /media/avatars/{key}/image``)?
    has_image: bool = False


@dataclass(frozen=True, slots=True)
class MediaOptions:
    voices: list[OptionView]
    avatars: list[OptionView]
    own_voice: bool
    own_avatar: bool
    selected: Choice
    defaults: Choice


@dataclass(frozen=True, slots=True)
class _Providers:
    tts: str
    avatar: str
    avatar_accepts_image: bool


def catalog(settings: Settings) -> MediaCatalog:
    return load_catalog(settings.media_config)


def _providers(registry: ProviderRegistry) -> _Providers:
    avatar = registry.avatar("realtime")
    return _Providers(
        tts=registry.provider_name("tts", "realtime"),
        avatar=avatar.name,
        avatar_accepts_image=avatar.accepts_image,
    )


def _usable_avatar(option: MediaOption, providers: _Providers) -> bool:
    value = option.ids.get(providers.avatar)
    if value is None:
        return False
    return providers.avatar_accepts_image or not value.startswith(FILE_PREFIX)


def _available_keys(cat: MediaCatalog, providers: _Providers, kind: MediaKind) -> list[str]:
    if kind == "voice":
        return [o.key for o in cat.available("voice", providers.tts)]
    return [o.key for o in cat.avatars.values() if _usable_avatar(o, providers)]


async def _own(db: AsyncSession, user: User, providers: _Providers, kind: MediaKind) -> bool:
    """Kullanıcının bu türde, şu anki sağlayıcıyla kullanılabilir rızalı kaydı var mı?"""
    asset = await biometric_service.active_asset(
        db, user.id, "voice" if kind == "voice" else "face"
    )
    provider = providers.tts if kind == "voice" else providers.avatar
    return asset is not None and asset.provider == provider


async def _preference(db: AsyncSession, user: User, persona: Persona) -> MediaPreference | None:
    return await db.scalar(
        select(MediaPreference).where(
            MediaPreference.user_id == user.id, MediaPreference.persona_id == persona.id
        )
    )


def _defaults(cat: MediaCatalog, persona: Persona) -> Choice:
    slug = persona.slug or "eva"
    try:
        return Choice(voice=cat.default(slug, "voice"), avatar=cat.default(slug, "avatar"))
    except MediaNotConfiguredError:
        return Choice(voice=cat.default("eva", "voice"), avatar=cat.default("eva", "avatar"))


async def chosen(
    db: AsyncSession,
    settings: Settings,
    registry: ProviderRegistry,
    user: User,
    persona: Persona,
) -> Choice:
    """Bu persona için geçerli seçim. Kayıtlı seçim artık katalogda yoksa (ayar değişti)
    varsayılana döner; "own" olduğu gibi kalır (kullanılamıyorsa görüşme açıkça hata verir)."""
    cat = catalog(settings)
    providers = _providers(registry)
    defaults = _defaults(cat, persona)
    pref = await _preference(db, user, persona)

    def pick(value: str | None, kind: MediaKind, default: str) -> str:
        if value == OWN or (value and value in _available_keys(cat, providers, kind)):
            return value
        return default

    return Choice(
        voice=pick(pref.voice_key if pref else None, "voice", defaults.voice),
        avatar=pick(pref.avatar_key if pref else None, "avatar", defaults.avatar),
    )


async def options(
    db: AsyncSession,
    settings: Settings,
    registry: ProviderRegistry,
    user: User,
    persona: Persona,
) -> MediaOptions:
    cat = catalog(settings)
    providers = _providers(registry)
    return MediaOptions(
        voices=[OptionView(o.key, o.name) for o in cat.available("voice", providers.tts)],
        avatars=[
            OptionView(
                o.key,
                o.name,
                has_image=any(v.startswith(FILE_PREFIX) for v in o.ids.values()),
            )
            for o in cat.avatars.values()
            if _usable_avatar(o, providers)
        ],
        own_voice=await _own(db, user, providers, "voice"),
        own_avatar=await _own(db, user, providers, "avatar"),
        selected=await chosen(db, settings, registry, user, persona),
        defaults=_defaults(cat, persona),
    )


async def set_preference(
    db: AsyncSession,
    settings: Settings,
    registry: ProviderRegistry,
    user: User,
    persona: Persona,
    *,
    voice: str | None,
    avatar: str | None,
) -> None:
    """``None`` = personanın varsayılanı. "own" yalnızca aktif, rızalı bir kayıt varsa."""
    cat = catalog(settings)
    providers = _providers(registry)
    wanted: list[tuple[MediaKind, str | None]] = [("voice", voice), ("avatar", avatar)]
    for kind, value in wanted:
        if value is None:
            continue
        if value == OWN:
            if not await _own(db, user, providers, kind):
                raise MediaChoiceError("no_active_voice" if kind == "voice" else "no_active_avatar")
        elif value not in _available_keys(cat, providers, kind):
            raise MediaChoiceError(f"unknown_{kind}", status=422)

    pref = await _preference(db, user, persona)
    if pref is None:
        pref = MediaPreference(user_id=user.id, persona_id=persona.id)
        db.add(pref)
    pref.voice_key = voice
    pref.avatar_key = avatar
    await db.commit()


async def voice_preview(
    settings: Settings, registry: ProviderRegistry, user: User, key: str
) -> bytes:
    """Hazır bir sesi sabit bir cümleyle dinletir. Kendi klon sesin önizlemesi ayrı
    (``/biometrics/voice/preview``; rıza ve denetim kaydı orada)."""
    tts = registry.tts("preview")
    try:
        voice_id = catalog(settings).provider_id("voice", key, tts.name)
    except MediaNotConfiguredError as exc:
        raise MediaChoiceError("unknown_voice", status=404) from exc
    fmt = AudioFormat(sample_rate=24_000)
    sentence = VOICE_PREVIEW_SENTENCE["en" if user.locale == "en" else "tr"]

    async def text() -> AsyncIterator[str]:
        yield sentence

    request = TTSRequest(voice_id=voice_id, language=user.locale, output=fmt)
    pcm = b"".join([chunk.data async for chunk in tts.synthesize(text(), request)])
    return biometric_service.pcm_to_wav(pcm, fmt.sample_rate)


def avatar_image(settings: Settings, key: str) -> EnrollmentSample:
    """Katalogdaki bir yüzün yerel görseli (seçim ekranındaki küçük resim için)."""
    cat = catalog(settings)
    option = cat.avatars.get(key)
    value = next(
        (v for v in (option.ids.values() if option else ()) if v.startswith(FILE_PREFIX)), None
    )
    if value is None:
        raise MediaChoiceError("no_image", status=404)
    try:
        return media_image(cat.path, value)
    except MediaNotConfiguredError as exc:
        raise MediaChoiceError("no_image", status=404) from exc


async def persona_for(db: AsyncSession, user: User, persona_id: uuid.UUID | None) -> Persona:
    if persona_id is None:
        return await persona_service.get_default_eva(db)
    return await persona_service.get_persona_for_user(db, user, persona_id)
