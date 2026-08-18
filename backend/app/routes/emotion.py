"""
routes/emotion.py - Duygu Algılama WebSocket Endpoint'i (Faz 5 — Tam Sürüm)
==============================================================================
WS /ws/emotion?token=<JWT>  →  Video framelerini alır, DeepFace ile analiz eder,
3 katmanlı güvenlik filtresinden geçirip duygu etiketi döndürür.

📚 Akış:
    1. Frontend kamera açar → WebSocket bağlantısı kurar (JWT doğrulamalı)
    2. Her 3 saniyede bir base64 JPEG frame gelir
    3. DeepFace ile yüz ifadesi analizi yapılır
    4. 3 katmanlı güvenlik filtresi uygulanır:
       - Güven skoru < %75 → nötr
       - Metin ile çelişki → metin kazanır
       - Hafıza ile çelişki → anomali olarak filtrele
    5. Nihai duygu etiketi frontend'e gönderilir
    6. Frontend bu etiketi chat mesajıyla birlikte LLM'e gönderir

📚 JWT Doğrulama — WebSocket'te Farklı:
    Normal HTTP endpoint: Authorization header'dan token alınır
    WebSocket: Header gönderilmez! → Token query parameter ile gelir
    Örn: ws://localhost:8000/ws/emotion?token=eyJhbGci...
"""

import json
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.auth import decode_token
from app.core.emotion_analyzer import analyze_emotion, apply_confidence_filter, EMOTION_LABELS_TR
from app.database import SessionLocal
from app.models.user import User


router = APIRouter()
logger = logging.getLogger("eva.emotion")

# DeepFace CPU-bound iş olduğu için ayrı thread pool'da çalıştırıyoruz
# Bu sayede WebSocket event loop bloklanmaz
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="deepface")


async def _authenticate_websocket(websocket: WebSocket) -> User | None:
    """
    WebSocket bağlantısında JWT doğrulaması yapar.

    Nasıl çalışır:
    1. URL'den token query parametresini al
    2. decode_token() ile JWT'yi çöz
    3. DB'den kullanıcıyı bul
    4. Geçerliyse User döndür, değilse None

    📚 Not: HTTP endpoint'lerdeki get_current_user() burada kullanılamaz
    çünkü WebSocket'lerde Depends(security) yani HTTPBearer çalışmaz.
    Bu yüzden doğrulamayı manuel yapıyoruz.
    """
    # 1. Token'ı query parametresinden al
    token = websocket.query_params.get("token")
    if not token:
        logger.warning("WS bağlantısı reddedildi: Token eksik")
        return None

    # 2. JWT'yi çöz
    token_data = decode_token(token)
    if token_data is None:
        logger.warning("WS bağlantısı reddedildi: Geçersiz/süresi dolmuş token")
        return None

    # 3. Kullanıcıyı DB'den bul
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == token_data.user_id).first()
        if user is None or not user.is_active:
            logger.warning(f"WS bağlantısı reddedildi: Kullanıcı bulunamadı (ID: {token_data.user_id})")
            return None
        return user
    finally:
        db.close()


@router.websocket("/ws/emotion")
async def emotion_websocket(websocket: WebSocket):
    """
    Duygu algılama WebSocket endpoint'i.

    Gelen mesaj formatı:
    {
        "type": "frame",
        "data": "data:image/jpeg;base64,/9j/4AAQ..."   ← base64 JPEG
    }

    Dönen mesaj formatı:
    {
        "type": "emotion",
        "emotion": "happy",           ← duygu etiketi (İngilizce)
        "emotion_tr": "mutlu",        ← duygu etiketi (Türkçe)
        "confidence": 0.87,           ← güven skoru (0-1)
        "filtered": false             ← güvenlik filtresi uygulandı mı?
    }

    Desteklenen duygu etiketleri:
    happy, sad, angry, surprise, fear, disgust, neutral
    """

    # ─── ADIM 1: JWT Doğrulama ──────────────────────────────────────
    user = await _authenticate_websocket(websocket)

    if user is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Yetkisiz: Geçersiz veya eksik token")
        return

    # ─── ADIM 2: Bağlantıyı Kabul Et ────────────────────────────────
    await websocket.accept()
    logger.info(f"🎥 Emotion WS bağlantısı kuruldu: {user.username} (ID: {user.id})")

    try:
        # ─── ADIM 3: Mesaj Döngüsü ──────────────────────────────────
        while True:
            # Frontend'den mesaj bekle
            raw_data = await websocket.receive_text()

            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.warning(f"Bozuk JSON alındı ({user.username})")
                await websocket.send_json({
                    "type": "error",
                    "message": "Geçersiz JSON formatı"
                })
                continue

            msg_type = data.get("type")

            # ── Frame İşleme (DeepFace Analizi) ─────────────────────
            if msg_type == "frame":
                frame_data = data.get("data")

                if not frame_data:
                    continue

                try:
                    # ═══════════════════════════════════════════════════
                    # DeepFace analizi CPU-bound iştir.
                    # asyncio event loop'u bloklamemak için ThreadPool'da çalıştırıyoruz.
                    #
                    # 📚 run_in_executor():
                    #     Senkron (CPU ağır) fonksiyonu ayrı thread'de çalıştırır.
                    #     Ana event loop (WebSocket dinleme) bloklanmaz.
                    # ═══════════════════════════════════════════════════
                    loop = asyncio.get_event_loop()
                    raw_result = await loop.run_in_executor(
                        _executor,
                        analyze_emotion,
                        frame_data
                    )

                    # Katman 1: Güven skoru filtresi (%75 eşik)
                    # (Katman 2 ve 3, chat mesajı gönderildiğinde routes/chat.py'da uygulanır)
                    filtered_result = apply_confidence_filter(raw_result)

                    emotion_response = {
                        "type": "emotion",
                        "emotion": filtered_result["emotion"],
                        "emotion_tr": EMOTION_LABELS_TR.get(filtered_result["emotion"], "nötr"),
                        "confidence": filtered_result["confidence"],
                        "filtered": filtered_result["emotion"] != raw_result.get("emotion", "neutral")
                    }

                    await websocket.send_json(emotion_response)

                except Exception as e:
                    logger.error(f"Frame analiz hatası ({user.username}): {e}")
                    # Hata durumunda neutral gönder — frontend'i kırmamak için
                    await websocket.send_json({
                        "type": "emotion",
                        "emotion": "neutral",
                        "emotion_tr": "nötr",
                        "confidence": 0.0,
                        "filtered": False
                    })

            # ── Ping/Pong (Bağlantı Canlılık Kontrolü) ──────────
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            # ── Bilinmeyen Mesaj Tipi ────────────────────────────
            else:
                logger.debug(f"Bilinmeyen mesaj tipi: {msg_type} ({user.username})")

    except WebSocketDisconnect:
        logger.info(f"🎥 Emotion WS bağlantısı kapandı: {user.username}")

    except Exception as e:
        logger.error(f"Emotion WS hatası ({user.username}): {str(e)}")
        try:
            await websocket.close(code=1011, reason="Sunucu hatası")
        except RuntimeError:
            pass
