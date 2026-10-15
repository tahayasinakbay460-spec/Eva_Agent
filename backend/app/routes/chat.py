"""
routes/chat.py - Sohbet API Endpoint'leri (FastAPI)
=====================================================
POST /api/chat          → Eva ile konuşma (JWT korumalı)
GET  /api/chat/memory-stats → Hafıza istatistikleri (JWT korumalı)
WS   /ws/chat           → Eva streaming (JWT token query param)

Faz 2: Tüm endpoint'ler artık JWT token gerektiriyor.
Faz 3: Mesajlar artık MySQL'deki messages tablosuna da kaydediliyor.
Faz 9: WebSocket streaming — token token akış.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
import json
import asyncio
from typing import List
from app.schemas.chat import ChatRequest, ChatResponse, MemoryStatsResponse, CancelRequest
from app.core.eva_agent import chat_with_eva, chat_with_eva_stream
from app.core.memory import get_memory

# Global tracking set for cancelled requests
CANCELLED_REQUESTS = set()
from app.core.dependencies import get_current_user
from app.core.auth import decode_token          # JWT WebSocket doğrulama
from app.models.user import User
from app.models.chat import Conversation, Message
from app.database import get_db, SessionLocal

router = APIRouter()


def _get_or_create_conversation(db: Session, user_id: int, conv_id: int | None,
                                first_message: str) -> Conversation:
    """
    Aktif sohbet oturumunu döndürür veya yeni oluşturur.
    conv_id verilirse o sohbet yüklenir, yoksa yeni sohbet başlatılır.
    Sohbetin başlığı otomatik olarak ilk mesajın ilk 60 karakterinden alınır.
    """
    if conv_id:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.user_id == user_id,
            Conversation.ancestor_id.is_(None),
        ).first()
        if conv:
            return conv

    # Yeni sohbet — başlık için ilk mesajın ilk 60 karakterini al
    title = first_message[:60].strip()
    if len(first_message) > 60:
        title += "…"

    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),   # JWT zorunlu
    db: Session = Depends(get_db)
):
    """
    Ana sohbet endpoint'i — JWT korumalı.
    Mesajlar MySQL'e kaydedilir ve sol panelde görünür.
    """
    print(f"\n[{current_user.username}#{current_user.id}]: {request.message}")
    if request.detected_emotion:
        print(f"  [DUYGU] Kamera duygusu: {request.detected_emotion}")

    try:
        history_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        # Sohbet oturumunu bul ya da oluştur
        conv = _get_or_create_conversation(
            db=db,
            user_id=current_user.id,
            conv_id=getattr(request, "conversation_id", None),
            first_message=request.message
        )

        # 1. Kullanıcı mesajını HEMEN kaydet
        db.add(Message(conversation_id=conv.id, role="user", content=request.message))
        conv.updated_at = datetime.utcnow()
        db.commit()

        # Yapay zekaya gönder (Faz 5: duygu etiketi de eklendi)
        eva_response = chat_with_eva(
            user_message=request.message,
            user_id=str(current_user.id),
            conversation_history=history_dicts,
            detected_emotion=request.detected_emotion  # Faz 5: Kameradan gelen duygu
        )

        print(f"Eva -> {current_user.username}: {eva_response[:80].encode('ascii', errors='ignore').decode('ascii')}...")

        # 2. İptal Kontrolü
        if request.tracking_id and request.tracking_id in CANCELLED_REQUESTS:
            CANCELLED_REQUESTS.remove(request.tracking_id)
            print(f"İSTEK İPTAL EDİLDİ (tracking_id: {request.tracking_id}). Eva'nın yanıtı veritabanına kaydedilmedi.")
            return ChatResponse(
                response="",
                user_id=str(current_user.id),
                conversation_id=conv.id
            )

        # 3. Eva'nın mesajını kaydet
        db.add(Message(conversation_id=conv.id, role="assistant", content=eva_response))
        conv.updated_at = datetime.utcnow()
        db.commit()

        return ChatResponse(
            response=eva_response,
            user_id=str(current_user.id),
            conversation_id=conv.id
        )

    except ValueError as ve:
        # LLM sağlayıcıları çöktüğünde (kota doldu, tüm fallback'ler tükendi)
        print(f"[LLM HATA] Tüm sağlayıcılar başarısız: {ve}")
        fallback_msg = (
            "Bir sorun oluştu, lütfen tekrar dene."
        )
        return ChatResponse(
            response=fallback_msg,
            user_id=str(current_user.id),
            conversation_id=getattr(conv, 'id', 0) if 'conv' in locals() else 0
        )
    except Exception as e:
        safe_error = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f"Hata: {safe_error}")
        raise HTTPException(
            status_code=500,
            detail=f"Eva şu an düşünemedi: {safe_error}"
        )


@router.get("/chat/memory-stats", response_model=MemoryStatsResponse)
def memory_stats(
    current_user: User = Depends(get_current_user)   # JWT zorunlu
):
    """Mevcut kullanıcının hafıza istatistikleri."""
    memory = get_memory()
    count = memory.get_memory_count(str(current_user.id))

    return MemoryStatsResponse(
        user_id=str(current_user.id),
        memory_count=count,
        message=f"Eva'nın {current_user.username} için {count} konuşma kaydı var."
    )

@router.post("/chat/cancel")
def cancel_chat(request: CancelRequest):
    """Kullanıcı sohbeti iptal ettiğinde backend'i haberdar eder."""
    if request.tracking_id:
        CANCELLED_REQUESTS.add(request.tracking_id)
    return {"status": "cancelled"}


# ═══════════════════════════════════════════════════════════════════════
# WEBSOCKET STREAMİNG ENDPOINT  (Faz 9)
# ═══════════════════════════════════════════════════════════════════════

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket Streaming Chat — Faz 9
    ==================================
    Bağlantı: ws://localhost:8000/api/ws/chat?token=<JWT>

    Protokol:
      → Kullanıcı JSON gönderir:
         { "message": "...", "history": [...], "conversation_id": null }
      ← Eva token token text yollar (her chunk ayrı mesaj)
      ← Stream bittiğinde: {"type": "done", "conversation_id": 123}
      ← Hata olursa:       {"type": "error", "detail": "..."}
    """
    await websocket.accept()

    # ── 1. JWT doğrula ──────────────────────────────────────────────
    token_data = decode_token(token)
    if not token_data:
        await websocket.send_json({"type": "error", "detail": "Geçersiz token."})
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        from app.models.user import User as UserModel
        user = db.query(UserModel).filter(UserModel.id == token_data.user_id).first()
        if not user:
            await websocket.send_json({"type": "error", "detail": "Kullanıcı bulunamadı."})
            await websocket.close(code=1008)
            return

        print(f"[WS] Bağlantı: {user.username}#{user.id}")

        while True:
            # ── 2. Kullanıcıdan mesaj al ─────────────────────────────
            try:
                raw = await websocket.receive_text()
                data = json.loads(raw)
            except WebSocketDisconnect:
                print(f"[WS] Bağlantı kesildi: {user.username}")
                break
            except Exception as e:
                await websocket.send_json({"type": "error", "detail": str(e)})
                continue

            user_message  = data.get("message", "").strip()
            history       = data.get("history", [])
            conv_id       = data.get("conversation_id", None)
            detected_emo  = data.get("detected_emotion", None)

            if not user_message:
                continue

            print(f"[WS] {user.username}: {user_message[:60]}")

            # ── 3. Sohbet oturumunu bul / oluştur ───────────────────
            conv = _get_or_create_conversation(
                db=db,
                user_id=user.id,
                conv_id=conv_id,
                first_message=user_message
            )

            # Kullanıcı mesajını hemen DB'ye kaydet
            db.add(Message(conversation_id=conv.id, role="user", content=user_message))
            conv.updated_at = datetime.utcnow()
            db.commit()

            # ── 4. Streaming — token token gönder (thread'de çalışır) ───
            full_response_parts = []
            try:
                import threading
                q = asyncio.Queue()
                SENTINEL = object()

                # ✔ Loop'u thread başlamadan önce yakala — thread içinden
                #   asyncio.get_event_loop() çağırmak Python 3.10+'da güvensiz.
                captured_loop = asyncio.get_event_loop()

                def _produce():
                    """Thread'de çalışır: her token'u event loop üzerinden kuyruğa iter."""
                    try:
                        for chunk in chat_with_eva_stream(
                            user_message=user_message,
                            user_id=str(user.id),
                            conversation_history=history,
                            detected_emotion=detected_emo,
                        ):
                            if chunk:
                                captured_loop.call_soon_threadsafe(q.put_nowait, chunk)
                    except Exception as prod_err:
                        # Hata olursa frontend'e ilet
                        captured_loop.call_soon_threadsafe(
                            q.put_nowait, f"[HATA] {prod_err}"
                        )
                    finally:
                        captured_loop.call_soon_threadsafe(q.put_nowait, SENTINEL)

                t = threading.Thread(target=_produce, daemon=True)
                t.start()

                # Ana async döngü: kuyruktan oku, WebSocket'e gönder
                while True:
                    item = await asyncio.wait_for(q.get(), timeout=60.0)
                    if item is SENTINEL:
                        break
                    full_response_parts.append(item)
                    await websocket.send_text(item)

            except asyncio.TimeoutError:
                await websocket.send_json({"type": "error", "detail": "Zaman aşımı (60s)"})
                continue
            except Exception as e:
                await websocket.send_json({"type": "error", "detail": str(e)})
                continue

            # ── 5. Stream bitti — DB'ye kaydet ve bitti sinyali gönder
            full_response = "".join(full_response_parts)
            if full_response.strip():
                db.add(Message(conversation_id=conv.id, role="assistant", content=full_response))
                conv.updated_at = datetime.utcnow()
                db.commit()

            # Frontend'e "stream bitti" sinyali + conversation_id
            await websocket.send_json({
                "type": "done",
                "conversation_id": conv.id
            })

    finally:
        db.close()
