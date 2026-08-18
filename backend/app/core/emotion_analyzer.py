"""
core/emotion_analyzer.py - Duygu Analizi Motoru (Faz 5.2 + 5.3)
================================================================
DeepFace ile yüz ifadesinden duygu tespiti + 3 katmanlı güvenlik filtresi.

📚 Öğretici Not — DeepFace Nedir?
    DeepFace = Facebook'un geliştirdiği açık kaynak yüz analizi kütüphanesi.
    analyze() fonksiyonu bir yüz fotoğrafını alır ve şunları döndürür:
    - emotion:  {angry: 2.1, happy: 85.3, sad: 0.5, ...}
    - age:      tahmini yaş
    - gender:   cinsiyet
    - race:     etnik köken (biz bunu kullanmıyoruz)

    Biz sadece emotion (duygu) kısmını kullanıyoruz.

📚 3 Katmanlı Güvenlik Filtresi:
    1. Güven Skoru (Confidence Threshold):
       CV modelinin duygu tespiti %75'in altındaysa → "nötr" kabul et
    
    2. Metin Hiyerarşisi:
       Kullanıcının metin duygusu, kamera duygsuyla çelişirse → metin kazanır
    
    3. Hafıza (Bağlam) Filtresi:
       ChromaDB geçmişi pozitifse, anlık negatif frameler → anomali olarak filtrele

Desteklenen Duygu Etiketleri:
    happy, sad, angry, surprise, fear, disgust, neutral
    
    Türkçe karşılıkları (LLM prompt'unda kullanılır):
    mutlu, üzgün, kızgın/sinirli, şaşkın, korkmuş, iğrenmiş, nötr
"""

import base64
import io
import logging
import numpy as np
from PIL import Image
from typing import Optional

logger = logging.getLogger("eva.emotion")

# ─── DeepFace Lazy Loading ──────────────────────────────────────────────────
# DeepFace import'u ağırdır (~3-5 saniye, TensorFlow yükler).
# Bu yüzden ilk frame gelene kadar yüklenmez (lazy loading).
_deepface_loaded = False
_DeepFace = None


def _load_deepface():
    """
    DeepFace'i lazy olarak yükler.
    İlk çağrıda ~3-5 saniye sürer (model dosyaları indirilir).
    Sonraki çağrılarda anında döner.
    """
    global _deepface_loaded, _DeepFace
    if _deepface_loaded:
        return _DeepFace
    
    try:
        from deepface import DeepFace
        _DeepFace = DeepFace
        _deepface_loaded = True
        logger.info("✅ DeepFace modeli yüklendi")
        return _DeepFace
    except ImportError as e:
        logger.error(f"❌ DeepFace import hatası: {e}")
        logger.error("Çözüm: pip install deepface tf-keras")
        return None
    except Exception as e:
        logger.error(f"❌ DeepFace yükleme hatası: {e}")
        return None


# ─── Sabitler ────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.75  # %75'in altındaki duygu tespitleri → nötr

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

# Pozitif ve negatif duygu grupları (hafıza filtresi için)
POSITIVE_EMOTIONS = {"happy", "surprise"}
NEGATIVE_EMOTIONS = {"sad", "angry", "fear", "disgust"}


def base64_to_numpy(base64_data: str) -> Optional[np.ndarray]:
    """
    Base64 JPEG string'i numpy array'e çevirir (DeepFace'in beklediği format).
    
    📚 Akış:
        "data:image/jpeg;base64,/9j/4AAQ..."  →  saf base64  →  bytes  →  PIL Image  →  numpy array
    
    Args:
        base64_data: Frontend'den gelen "data:image/jpeg;base64,..." formatında string
    
    Returns:
        numpy.ndarray (H, W, 3) RGB formatında veya None (hata durumunda)
    """
    try:
        # "data:image/jpeg;base64," prefix'ini temizle
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        
        # Base64 → bytes → PIL Image → numpy
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))
        image_rgb = image.convert("RGB")
        return np.array(image_rgb)
    
    except Exception as e:
        logger.warning(f"Frame dönüştürme hatası: {e}")
        return None


def analyze_emotion(frame_base64: str) -> dict:
    """
    Bir video frame'inden duygu analizi yapar.
    
    📚 DeepFace.analyze() Parametreleri:
        img_path:       numpy array veya dosya yolu
        actions:        ['emotion'] — sadece duygu analizi (age, gender istemiyoruz)
        enforce_face_detection: False → yüz bulunamazsa hata fırlatma, boş dön
        detector_backend: 'opencv' — en hızlı yüz tespit motoru
        silent:         True → gereksiz log çıktılarını engelle
    
    Returns:
        {
            "emotion": "happy",
            "emotion_tr": "mutlu",
            "confidence": 0.87,
            "all_emotions": {"angry": 2.1, "happy": 87.3, ...}
        }
        
        Yüz bulunamazsa veya hata olursa:
        {
            "emotion": "neutral",
            "emotion_tr": "nötr",
            "confidence": 0.0,
            "all_emotions": {}
        }
    """
    # Varsayılan sonuç (yüz bulunamadı / hata durumu)
    default_result = {
        "emotion": "neutral",
        "emotion_tr": "nötr",
        "confidence": 0.0,
        "all_emotions": {}
    }
    
    # DeepFace'i yükle
    DeepFace = _load_deepface()
    if DeepFace is None:
        return default_result
    
    # Base64'ü numpy array'e çevir
    frame_array = base64_to_numpy(frame_base64)
    if frame_array is None:
        return default_result
    
    try:
        # DeepFace analizi — sadece emotion
        results = DeepFace.analyze(
            img_path=frame_array,
            actions=["emotion"],
            enforce_detection=False,        # Yüz yoksa hata fırlatma (Faz 5: yeni sürümlerde adı enforce_detection)
            detector_backend="opencv",      # En hızlı detector
            silent=True                     # Log spam'i engelle
        )
        
        # DeepFace liste döndürebilir (birden fazla yüz)
        if isinstance(results, list):
            if len(results) == 0:
                return default_result
            result = results[0]  # İlk yüzü al
        else:
            result = results
        
        # Duygu skorlarını al
        emotions = result.get("emotion", {})
        if not emotions:
            return default_result
        
        # En yüksek skora sahip duyguyu bul
        dominant_emotion = max(emotions, key=emotions.get)
        confidence = emotions[dominant_emotion] / 100.0  # 0-1 aralığına çevir
        
        return {
            "emotion": dominant_emotion,
            "emotion_tr": EMOTION_LABELS_TR.get(dominant_emotion, "nötr"),
            "confidence": round(confidence, 3),
            "all_emotions": {k: round(v / 100.0, 3) for k, v in emotions.items()}
        }
    
    except Exception as e:
        logger.warning(f"DeepFace analiz hatası: {e}")
        return default_result


# ══════════════════════════════════════════════════════════════════════════════
# FAZ 5.3 — 3 KATMANLI GÜVENLİK FİLTRESİ
# ══════════════════════════════════════════════════════════════════════════════

def apply_confidence_filter(emotion_result: dict) -> dict:
    """
    Katman 1: Güven Skoru Filtresi
    
    📚 Neden?
        CV modelleri her zaman %100 doğru değil. Bulanık görüntü, ışık sorunu,
        el yüzün önünde vs. durumlarda model yanlış duygu verebilir.
        
        Kural: Confidence < %75 → duyguyu "nötr" kabul et.
        Böylece düşük güvenilirlikli tespitler Eva'yı yanıltmaz.
    
    Args:
        emotion_result: analyze_emotion()'dan gelen dict
    
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
        Ham kamera duygusu
            → [Katman 1] Güven skoru filtresi (%75 eşik)
            → [Katman 2] Metin hiyerarşisi (metin > kamera)
            → [Katman 3] Hafıza filtresi (anomali tespiti)
            → Nihai duygu etiketi
    
    Args:
        camera_emotion_result: analyze_emotion()'dan gelen ham sonuç
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
