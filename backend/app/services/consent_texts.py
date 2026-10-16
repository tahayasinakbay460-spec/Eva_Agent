"""Rıza metinleri (§11.3). Sürümlüdür: rıza kaydı hangi sürümün onaylandığını ve metnin
özetini saklar. Metin değişirse ``VERSION`` artırılır; eski kayıtlar eski sürümle kalır.

Bunlar hukuki metinlerdir; lansmandan önce KVKK/AB alanında uzman bir avukat incelemeli (§12).
"""

import hashlib
from typing import Literal

Kind = Literal["voice", "face"]
Locale = Literal["tr", "en"]

VERSION = "2026-10-16"

PURPOSE: dict[Kind, str] = {"voice": "voice_clone", "face": "face_avatar"}

_SUMMARY: dict[Locale, dict[Kind, str]] = {
    "tr": {
        "voice": (
            "Ses kaydın, EVA'da senin sesine benzeyen yapay bir ses (ses klonu) oluşturmak için "
            "kullanılacak. Kayıtların bizde şifreli saklanır; klon, ses sağlayıcımızda (şu an "
            "ElevenLabs) oluşturulur ve sağlayıcıda yalnızca bir kimlik numarası olarak tutulur. "
            "Klonla üretilen ses indirilemez ve uygulama dışına paylaşılamaz. Kaydın bir kişi "
            "tarafından incelenir; onaylanmadan klon oluşturulmaz. Bu izni istediğin an geri "
            "alabilirsin: kullanım anında durur, klon sağlayıcıdan silinir ve kayıtların imha "
            "edilir."
        ),
        "face": (
            "Yüz videon, EVA'da senin yüzüne benzeyen konuşan bir avatar oluşturmak için "
            "kullanılacak. Videoların bizde şifreli saklanır; avatar, avatar sağlayıcımızda "
            "oluşturulur ve sağlayıcıda yalnızca bir kimlik numarası olarak tutulur. Avatarla "
            "üretilen görüntü indirilemez ve uygulama dışına paylaşılamaz. Kaydın bir kişi "
            "tarafından incelenir; onaylanmadan avatar oluşturulmaz. Bu izni istediğin an geri "
            "alabilirsin: kullanım anında durur, avatar sağlayıcıdan silinir ve videoların imha "
            "edilir."
        ),
    },
    "en": {
        "voice": (
            "Your recordings will be used to create an artificial voice that sounds like you "
            "(a voice clone) inside EVA. We store them encrypted; the clone is created at our "
            "voice provider (currently ElevenLabs), which only keeps it under an ID. Audio made "
            "with the clone cannot be downloaded or shared outside the app. A person reviews your "
            "recording; nothing is cloned before approval. You can withdraw this consent at any "
            "time: use stops immediately, the clone is deleted at the provider and your recordings "
            "are destroyed."
        ),
        "face": (
            "Your video will be used to create a talking avatar that looks like you inside EVA. "
            "We store it encrypted; the avatar is created at our avatar provider, which only keeps "
            "it under an ID. Video made with the avatar cannot be downloaded or shared outside the "
            "app. A person reviews your recording; nothing is created before approval. You can "
            "withdraw this consent at any time: use stops immediately, the avatar is deleted at "
            "the provider and your videos are destroyed."
        ),
    },
}

_SENTENCE: dict[Locale, dict[Kind, str]] = {
    "tr": {
        "voice": (
            "Ben {name}. EVA'nın sesimi klonlamasına kendi isteğimle izin veriyorum. Bu izni "
            "istediğim zaman geri alabileceğimi biliyorum. Doğrulama kodum: {code}."
        ),
        "face": (
            "Ben {name}. EVA'nın yüzümden konuşan bir avatar oluşturmasına kendi isteğimle izin "
            "veriyorum. Bu izni istediğim zaman geri alabileceğimi biliyorum. Doğrulama kodum: "
            "{code}."
        ),
    },
    "en": {
        "voice": (
            "I am {name}. Of my own free will I allow EVA to clone my voice. I know I can withdraw "
            "this consent at any time. My verification code is {code}."
        ),
        "face": (
            "I am {name}. Of my own free will I allow EVA to create a talking avatar from my face. "
            "I know I can withdraw this consent at any time. My verification code is {code}."
        ),
    },
}

# Ses örneği kaydederken okunacak metin (yaklaşık 1 dakika). Sağlayıcı 1-2 dk temiz ses öneriyor.
READING_PASSAGE: dict[Locale, str] = {
    "tr": (
        "Sabah erkenden kalktım, pencereyi açtım ve derin bir nefes aldım. Hava serindi ama güneş "
        "yavaş yavaş ısıtmaya başlamıştı. Mutfağa geçip bir bardak çay demledim. Bir yandan "
        "radyoda eski şarkılar çalıyordu, bir yandan da bugün yapacaklarımı düşünüyordum. "
        "Önce pazara uğrayıp taze sebze alacak, sonra annemi arayacaktım. Öğleden sonra da "
        "arkadaşlarla sahilde buluşup uzun bir yürüyüş yapmayı planlamıştık. Bazen en güzel "
        "günler, hiçbir şeyin acele olmadığı, küçük şeylerin tadını çıkardığımız günlerdir. "
        "Rüzgârın sesi, denizin kokusu, uzaktan gelen martı çığlıkları... Hepsi insana iyi gelir. "
        "Akşam eve dönünce bir kitap açıp günü sakin sakin bitirmeyi seviyorum."
    ),
    "en": (
        "I woke up early this morning, opened the window and took a deep breath. The air was cool, "
        "but the sun was slowly starting to warm things up. I went to the kitchen and brewed a cup "
        "of tea. Old songs were playing on the radio while I thought about the day ahead. First I "
        "would stop by the market for fresh vegetables, then call my mother. In the afternoon my "
        "friends and I had planned a long walk by the sea. Sometimes the best days are the ones "
        "where nothing is rushed and we enjoy the little things. The sound of the wind, the smell "
        "of the sea, gulls calling in the distance... In the evening I like to open a book and end "
        "the day quietly."
    ),
}

# Ses önizlemesi yalnızca bu sabit cümlelerle yapılır: klon sesle keyfi konuşma üretilemez
# (sahte arama dolandırıcılığına karşı, §11.3).
PREVIEW_SENTENCES: dict[Locale, tuple[str, ...]] = {
    "tr": (
        "Merhaba, bu benim sesimin dijital bir kopyası.",
        "Bugün hava çok güzel, biraz yürüyüşe çıkmak iyi gelir.",
        "Seninle konuşmak her zaman keyifli.",
    ),
    "en": (
        "Hello, this is a digital copy of my voice.",
        "The weather is lovely today, a short walk would be nice.",
        "It is always a pleasure to talk with you.",
    ),
}


def _locale(locale: str) -> Locale:
    return "en" if locale == "en" else "tr"


def summary(kind: Kind, locale: str) -> str:
    return _SUMMARY[_locale(locale)][kind]


def spaced_code(code: str) -> str:
    """'472918' -> '4 7 2 9 1 8': sesli okununca rakam rakam anlaşılsın."""
    return " ".join(code)


def sentence(kind: Kind, locale: str, *, name: str, code: str) -> str:
    return _SENTENCE[_locale(locale)][kind].format(name=name, code=spaced_code(code))


def text_digest(kind: Kind, locale: str, *, name: str, code: str) -> str:
    """Onaylanan metnin özeti: özet + rıza cümlesi (kod dahil), sürümüyle birlikte."""
    body = f"{VERSION}\n{summary(kind, locale)}\n{sentence(kind, locale, name=name, code=code)}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
