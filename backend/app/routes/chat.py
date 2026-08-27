"""
routes/chat.py - Sohbet API Endpoint'leri (FastAPI)
=====================================================
POST /api/chat          → Eva ile konuşma (JWT korumalı)
GET  /api/chat/memory-stats → Hafıza istatistikleri (JWT korumalı)

Faz 2: Tüm endpoint'ler artık JWT token gerektiriyor.
Faz 3: Mesajlar artık MySQL'deki messages tablosuna da kaydediliyor.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.chat import ChatRequest, ChatResponse, MemoryStatsResponse
from app.core.eva_agent import chat_with_eva
from app.core.memory import get_memory
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.chat import Conversation, Message
from app.database import get_db

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
        print(f"  🎭 Kamera duygusu: {request.detected_emotion}")

    try:
        history_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        # Yapay zekaya gönder (Faz 5: duygu etiketi de eklendi)
        eva_response = chat_with_eva(
            user_message=request.message,
            user_id=str(current_user.id),
            conversation_history=history_dicts,
            detected_emotion=request.detected_emotion  # Faz 5: Kameradan gelen duygu
        )

        print(f"Eva -> {current_user.username}: {eva_response[:80].encode('ascii', errors='ignore').decode('ascii')}...")

        # Sohbet oturumunu bul ya da oluştur
        conv = _get_or_create_conversation(
            db=db,
            user_id=current_user.id,
            conv_id=getattr(request, "conversation_id", None),
            first_message=request.message
        )

        # İki mesajı da (kullanıcı + Eva) kaydet
        db.add(Message(conversation_id=conv.id, role="user",      content=request.message))
        db.add(Message(conversation_id=conv.id, role="assistant", content=eva_response))

        # Sohbetin updated_at'ini güncelle (sol panelde üste çıkar)
        conv.updated_at = datetime.utcnow()
        db.commit()

        return ChatResponse(
            response=eva_response,
            user_id=str(current_user.id),
            conversation_id=conv.id
        )

    except Exception as e:
        print(f"Hata: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Eva şu an düşünemedi: {str(e)}"
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
