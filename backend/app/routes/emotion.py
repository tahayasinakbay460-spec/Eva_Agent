"""
routes/emotion.py - Duygu Algılama WebSocket Endpoint'i (Faz 5.1)
==================================================================
WS /ws/emotion?token=<JWT>  →  Video framelerini alır, duygu etiketi döndürür.

📚 Öğretici Not — WebSocket vs HTTP:
    HTTP: İstek → Cevap → Bağlantı kapanır (her mesajda yeniden bağlan)
    WebSocket: Bağlantı bir kere kurulur → İki yönlü sürekli iletişim

    Neden WebSocket?
    - Video frameleri sürekli akıyor (saniyede 1 frame bile olsa)
    - HTTP'de her frame için yeni bağlantı açmak = gereksiz gecikme
    - WebSocket'te bağlantı açık kalır, veri anında akar

📚 JWT Doğrulama — WebSocket'te Farklı:
    Normal HTTP endpoint: Authorization header'dan token alınır
    WebSocket: Header gönderilmez! → Token query parameter ile gelir
    Örn: ws://localhost:8000/ws/emotion?token=eyJhbGci...

Faz 5.1: Placeholder — her frame'e "neutral" döner
Faz 5.2: DeepFace modeli entegre edilecek
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.auth import decode_token
from app.database import SessionLocal
from app.models.user import User


router = APIRouter()
logger = logging.getLogger("eva.emotion")


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

    Akış:
    1. Bağlantı gelir → JWT doğrula
    2. Geçerliyse kabul et, değilse 4001 ile kapat
    3. Frontend'den gelen frame mesajlarını dinle
    4. (Faz 5.2) DeepFace ile analiz et
    5. Duygu etiketini JSON olarak geri gönder

    Gelen mesaj formatı:
    {
        "type": "frame",
        "data": "data:image/jpeg;base64,/9j/4AAQ..."   ← base64 JPEG
    }

    Dönen mesaj formatı:
    {
        "type": "emotion",
        "emotion": "happy",           ← duygu etiketi
        "confidence": 0.87            ← güven skoru (0-1)
    }

    Desteklenen duygu etiketleri (Faz 5.2'de aktif olacak):
    happy, sad, angry, surprise, fear, disgust, neutral
    """

    # ─── ADIM 1: JWT Doğrulama ──────────────────────────────────────
    user = await _authenticate_websocket(websocket)

    if user is None:
        # Bağlantıyı kabul etmeden kapatamayız, önce kabul edip sonra kapatıyoruz
        # 📚 Not: WebSocket protokolü gereği, close() çağırmadan önce
        # accept() çağrılmalıdır, aksi halde bazı tarayıcılar hata verir
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

            # ── Frame İşleme ────────────────────────────────────────
            if msg_type == "frame":
                frame_data = data.get("data")

                if not frame_data:
                    continue

                # ═══════════════════════════════════════════════════
                # FAZ 5.2'DE BURADA DeepFace ÇAĞRILACAK
                # Şimdilik placeholder: her zaman "neutral" döndür
                # ═══════════════════════════════════════════════════
                emotion_result = {
                    "type": "emotion",
                    "emotion": "neutral",
                    "confidence": 0.0,
                    "debug": "Faz 5.1 placeholder — CV modeli henüz entegre edilmedi"
                }

                await websocket.send_json(emotion_result)

            # ── Ping/Pong (Bağlantı Canlılık Kontrolü) ──────────
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            # ── Bilinmeyen Mesaj Tipi ────────────────────────────
            else:
                logger.debug(f"Bilinmeyen mesaj tipi: {msg_type} ({user.username})")

    except WebSocketDisconnect:
        # Kullanıcı sayfayı kapattı veya bağlantıyı kesti — normal durum
        logger.info(f"🎥 Emotion WS bağlantısı kapandı: {user.username}")

    except Exception as e:
        # Beklenmeyen hata — loglayıp bağlantıyı kapat
        logger.error(f"Emotion WS hatası ({user.username}): {str(e)}")
        try:
            await websocket.close(code=1011, reason="Sunucu hatası")
        except RuntimeError:
            pass  # Bağlantı zaten kapalıysa RuntimeError oluşabilir
