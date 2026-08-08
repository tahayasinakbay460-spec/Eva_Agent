"""
routes/chat.py - Sohbet API Endpoint'leri (FastAPI)
=====================================================
POST /api/chat          → Eva ile konuşma (JWT korumalı)
GET  /api/chat/memory-stats → Hafıza istatistikleri (JWT korumalı)

Faz 2: Tüm endpoint'ler artık JWT token gerektiriyor.
user_id artık request body'den değil, doğrulanmış token'dan geliyor.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.chat import ChatRequest, ChatResponse, MemoryStatsResponse
from app.core.eva_agent import chat_with_eva
from app.core.memory import get_memory
from app.core.dependencies import get_current_user
from app.models.user import User
from app.database import get_db

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)   # JWT zorunlu
):
    """
    Ana sohbet endpoint'i — JWT korumalı.

    user_id artık request body'den gelmiyor.
    Doğrulanmış token'dan çekiliyor → manipüle edilemez.
    """
    print(f"\n[{current_user.username}#{current_user.id}]: {request.message}")

    try:
        history_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        eva_response = chat_with_eva(
            user_message=request.message,
            user_id=str(current_user.id),   # Güvenilir ID — token'dan geliyor
            conversation_history=history_dicts
        )

        print(f"Eva -> {current_user.username}: {eva_response[:80].encode('ascii', errors='ignore').decode('ascii')}...")

        return ChatResponse(
            response=eva_response,
            user_id=str(current_user.id)
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
    """
    Mevcut kullanıcının hafıza istatistikleri.
    user_id token'dan alınıyor — URL parametresi artık gerekmiyor.
    """
    memory = get_memory()
    count = memory.get_memory_count(str(current_user.id))

    return MemoryStatsResponse(
        user_id=str(current_user.id),
        memory_count=count,
        message=f"Eva'nın {current_user.username} için {count} konuşma kaydı var."
    )
