"""
core/emotion_analyzer.py - Duygu Filtre Motoru (Faz 5.3 + 6.5)
================================================================
3 katmanlı güvenlik filtresi — kameradan gelen duygu etiketini doğrular.

📚 Öğretici Not — Duygu Tespiti Nerede Yapılıyor?
    Eskiden: Backend'de DeepFace ile yapılıyordu (ağır, yavaş, TensorFlow).
    Şimdi:   Tarayıcıda face-api.js ile yapılıyor (anında, sıfır backend yükü).

    Bu dosya artık SADECE filtreleme yapar:
    Frontend duygu etiketini gönderir → burada 3 katmanlı filtreden geçer
    → nihai etiket LLM prompt'una enjekte edilir.

📚 3 Katmanlı Güvenlik Filtresi:
    1. Güven Skoru (Confidence Threshold):
       CV modelinin duygu tespiti eşiğin altındaysa → "nötr" kabul et

    2. Metin Hiyerarşisi:
       Kullanıcının metin duygusu, kamera duygusuyla çelişirse → metin kazanır

    3. Hafıza (Bağlam) Filtresi:
       ChromaDB geçmişi pozitifse, anlık negatif frameler → anomali olarak filtrele

Desteklenen Duygu Etiketleri:
    happy, sad, angry, surprise, fear, disgust, neutral

    Türkçe karşılıkları (LLM prompt'unda kullanılır):
    mutlu, üzgün, kızgın/sinirli, şaşkın, korkmuş, iğrenmiş, nötr
"""

import logging

logger = logging.getLogger("eva.emotion")


# ─── Sabitler ────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.40   # Bu eşiğin altındaki tespitler "nötr" sayılır

# Duygu etiketlerinin Türkçe karşılıkları (LLM prompt'unda kullanılır)
EMOTION_LABELS_TR = {
    "happy":    "mutlu",
    "sad":      "üzgün",
    "angry":    "kızgın",
    "surprise": "şaşkın",
    "fear":     "korkmuş",
    "disgust":  "iğrenmiş",
    "neutral":  "nötr",
}

# 📚 face-api.js farklı etiket isimleri kullanır (surprised, fearful, disgusted).
#    Backend standardına (surprise, fear, disgust) çevirmek için bu harita kullanılır.
#    Çevrilmezse "surprised" gibi etiketler tanınmaz ve duygu enjeksiyonu sessizce bozulur!
FACEAPI_LABEL_MAP = {
    "surprised": "surprise",
    "fearful":   "fear",
    "disgusted": "disgust",
}

# Pozitif ve negatif duygu grupları (hafıza filtresi için)
POSITIVE_EMOTIONS = {"happy", "surprise"}
NEGATIVE_EMOTIONS = {"sad", "angry", "fear", "disgust"}


def normalize_emotion_label(emotion: str) -> str:
    """
    face-api.js etiketini backend standardına çevirir.

    📚 Örnek:
        "surprised" → "surprise"
        "happy"     → "happy" (değişmez)
        None/boş    → "neutral"

    Args:
        emotion: Frontend'den gelen ham duygu etiketi

    Returns:
        Standartlaştırılmış duygu etiketi
    """
    if not emotion:
        return "neutral"
    emotion = emotion.strip().lower()
    return FACEAPI_LABEL_MAP.get(emotion, emotion)


# ══════════════════════════════════════════════════════════════════════════════
# FAZ 5.3 — 3 KATMANLI GÜVENLİK FİLTRESİ
# ══════════════════════════════════════════════════════════════════════════════

def apply_confidence_filter(emotion_result: dict) -> dict:
    """
    Katman 1: Güven Skoru Filtresi

    📚 Neden?
        CV modelleri her zaman %100 doğru değil. Bulanık görüntü, ışık sorunu,
        el yüzün önünde vs. durumlarda model yanlış duygu verebilir.

        Kural: Confidence < eşik → duyguyu "nötr" kabul et.
        Böylece düşük güvenilirlikli tespitler Eva'yı yanıltmaz.

    Args:
        emotion_result: {"emotion": ..., "confidence": ...} formatında dict

    Returns:
        Filtrelenmiş emotion_result (confidence düşükse neutral'e çevrilir)
    """
    if emotion_result["confidence"] < CONFIDENCE_THRESHOLD:
        logger.debug(
            f"Güven filtresi: {emotion_result['emotion']} "
            f"({emotion_result['confidence']:.0%}) < {CONFIDENCE_THRESHOLD:.0%} → nötr"
        )
        emotion_result["emotion"] = "neutral"
        emotion_result["emotion_tr"] = "nötr"
        # confidence değerini koruyoruz (debug için faydalı)

    return emotion_result


def apply_text_hierarchy(camera_emotion: str, text_sentiment: str) -> str:
    """
    Katman 2: Metin Hiyerarşisi

    📚 Neden?
        Kullanıcı "Çok mutluyum!" yazarken yüzü ekşi olabilir (düşünürken,
        ışık yüzüne vururken vs.). Bu durumda metin daha güvenilirdir.

        Kural: Metin duygusu ile kamera duygusu çelişirse → METİN KAZANIR.

    📚 Çelişki Nedir?
        Metin pozitif + Kamera negatif = ÇELİŞKİ → metin kazanır
        Metin negatif + Kamera pozitif = ÇELİŞKİ → metin kazanır
        Metin nötr + Kamera herhangi  = çelişki yok → kamera geçerli
        İkisi de aynı yönde           = çelişki yok → kamera geçerli

    Args:
        camera_emotion: Kameradan gelen duygu (happy, sad, angry...)
        text_sentiment: Metinden algılanan genel ton (positive, negative, neutral)

    Returns:
        Nihai duygu etiketi (camera_emotion veya text_sentiment'e göre override)
    """
    # Metin nötrse → kamera verisine karışma
    if text_sentiment == "neutral":
        return camera_emotion

    camera_is_positive = camera_emotion in POSITIVE_EMOTIONS
    camera_is_negative = camera_emotion in NEGATIVE_EMOTIONS

    # Çelişki kontrolü
    if text_sentiment == "positive" and camera_is_negative:
        logger.info(
            f"Metin hiyerarşisi: Metin=pozitif, Kamera={camera_emotion} → çelişki → metin kazandı (happy)"
        )
        return "happy"

    if text_sentiment == "negative" and camera_is_positive:
        logger.info(
            f"Metin hiyerarşisi: Metin=negatif, Kamera={camera_emotion} → çelişki → metin kazandı (sad)"
        )
        return "sad"

    # Çelişki yok → kamera geçerli
    return camera_emotion


def apply_memory_filter(camera_emotion: str, memory_sentiment: str) -> str:
    """
    Katman 3: Hafıza (Bağlam) Filtresi

    📚 Neden?
        Kullanıcı 10 dakikadır neşeli sohbet ediyorsa ve aniden tek bir frame
        "sad" geliyorsa, bu muhtemelen anlık bir anomali (hapşırma, gözlerini
        kısma, telefonuna bakma vs.).

        Kural: Sohbet geçmişi pozitifse, anlık negatif frameler → FİLTRELE.
        Tam tersi de geçerli: geçmiş negatifse, anlık pozitif → filtrele.

    Args:
        camera_emotion: Kameradan gelen duygu
        memory_sentiment: ChromaDB geçmiş analizi (positive, negative, neutral)

    Returns:
        Filtrelenmiş duygu etiketi
    """
    # Hafıza nötrse veya boşsa → filtreleme yapma
    if memory_sentiment == "neutral" or memory_sentiment == "":
        return camera_emotion

    camera_is_positive = camera_emotion in POSITIVE_EMOTIONS
    camera_is_negative = camera_emotion in NEGATIVE_EMOTIONS

    # Geçmiş pozitif + anlık negatif → anomali, nötre çevir
    if memory_sentiment == "positive" and camera_is_negative:
        logger.info(
            f"Hafıza filtresi: Geçmiş=pozitif, Kamera={camera_emotion} → anomali → nötr"
        )
        return "neutral"

    # Geçmiş negatif + anlık pozitif → anomali, nötre çevir
    if memory_sentiment == "negative" and camera_is_positive:
        logger.info(
            f"Hafıza filtresi: Geçmiş=negatif, Kamera={camera_emotion} → anomali → nötr"
        )
        return "neutral"

    return camera_emotion


def analyze_text_sentiment(text: str) -> str:
    """
    Basit kural tabanlı Türkçe metin duygu analizi.

    📚 Neden ML modeli değil?
        - Ek bağımlılık gerektirmez
        - Gecikme sıfır (anlık)
        - Türkçe için yeterli doğruluk (basit anahtar kelime eşleşmesi)
        - LLM zaten derin anlam çıkarıyor, bu sadece çelişki kontrolü için

    Returns:
        "positive", "negative", veya "neutral"
    """
    text_lower = text.lower()

    positive_words = {
        "mutlu", "sevinçli", "harika", "süper", "muhteşem", "güzel", "iyi",
        "seviyorum", "bayıldım", "mükemmel", "teşekkür", "sağol", "efsane",
        "heyecanlı", "şahane", "başarılı", "gurur", "keyifli", "neşeli",
        "sevindim", "çok iyi", "müthiş", "love", "happy", ":)", "😊",
        "😄", "❤️", "🎉", "👍", "💪", "🥳", "😁"
    }

    negative_words = {
        "üzgün", "kötü", "berbat", "korkunç", "sinirli", "kızgın", "nefret",
        "mutsuz", "stresli", "endişeli", "kaygılı", "depresif", "bıktım",
        "sıkıldım", "yoruldum", "korkuyorum", "acı", "ağlıyorum", "canım sıkılıyor",
        "rezalet", "felaket", "sad", "angry", "😢", "😭", "😡", "😤",
        "💔", "😞", "😰", "😥", "🤬", "ölmek", "intihar"
    }

    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"


def analyze_memory_sentiment(relevant_memories: str) -> str:
    """
    ChromaDB'den gelen geçmiş konuşmaların genel tonunu analiz eder.

    📚 Basit bir yaklaşım:
        Geçmiş konuşmalardaki pozitif/negatif kelime yoğunluğuna bakar.
        Derin analiz gerektirmez çünkü zaten özetlenmiş metinler.

    Args:
        relevant_memories: ChromaDB'den gelen birleştirilmiş geçmiş metin

    Returns:
        "positive", "negative", veya "neutral"
    """
    if not relevant_memories or len(relevant_memories.strip()) == 0:
        return "neutral"

    return analyze_text_sentiment(relevant_memories)


def get_filtered_emotion(
    camera_emotion_result: dict,
    user_message: str = "",
    relevant_memories: str = ""
) -> dict:
    """
    Tüm 3 güvenlik katmanını sırasıyla uygular ve nihai duygu etiketini döndürür.

    📚 Pipeline:
        Ham kamera duygusu (face-api.js etiketi)
            → Etiket normalizasyonu (surprised → surprise vb.)
            → [Katman 1] Güven skoru filtresi
            → [Katman 2] Metin hiyerarşisi (metin > kamera)
            → [Katman 3] Hafıza filtresi (anomali tespiti)
            → Nihai duygu etiketi

    Args:
        camera_emotion_result: {"emotion": ..., "confidence": ...} ham sonuç
        user_message: Kullanıcının son mesajı (metin hiyerarşisi için)
        relevant_memories: ChromaDB geçmişi (hafıza filtresi için)

    Returns:
        {
            "emotion": "happy",
            "emotion_tr": "mutlu",
            "confidence": 0.87,
            "filtered": True,          ← filtre uygulandı mı?
            "original_emotion": "sad"  ← filtrelenmeden önceki duygu
        }
    """
    # Etiketi backend standardına çevir (face-api.js uyumluluğu)
    camera_emotion_result["emotion"] = normalize_emotion_label(
        camera_emotion_result.get("emotion")
    )
    original_emotion = camera_emotion_result["emotion"]

    # Katman 1: Güven Skoru
    filtered = apply_confidence_filter(camera_emotion_result)
    current_emotion = filtered["emotion"]

    # Katman 2: Metin Hiyerarşisi (sadece kullanıcı mesajı varsa)
    if user_message:
        text_sentiment = analyze_text_sentiment(user_message)
        current_emotion = apply_text_hierarchy(current_emotion, text_sentiment)

    # Katman 3: Hafıza Filtresi (sadece geçmiş varsa)
    if relevant_memories:
        memory_sentiment = analyze_memory_sentiment(relevant_memories)
        current_emotion = apply_memory_filter(current_emotion, memory_sentiment)

    was_filtered = current_emotion != original_emotion

    return {
        "emotion": current_emotion,
        "emotion_tr": EMOTION_LABELS_TR.get(current_emotion, "nötr"),
        "confidence": camera_emotion_result["confidence"],
        "filtered": was_filtered,
        "original_emotion": original_emotion if was_filtered else None
    }
