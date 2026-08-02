"""
routes/chat.py - Sohbet API Endpoint'leri (FastAPI)
=====================================================
POST /api/chat          → Eva ile konuşma
GET  /api/chat/memory-stats → Hafıza istatistikleri

📚 Flask'taki değişiklikler:
    Blueprint → APIRouter
    request.get_json() → Pydantic modeli (otomatik)
    jsonify() → direkt dict veya Pydantic modeli döndür
    Hata yönetimi → HTTPException
"""

from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse, MemoryStatsResponse
from app.core.eva_agent import chat_with_eva
from app.core.memory import get_memory

# APIRouter = Flask'taki Blueprint'in karşılığı
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Ana sohbet endpoint'i.
    
    FastAPI, ChatRequest modelini otomatik olarak doğrular:
    - message boşsa 422 hatası döner (otomatik)
    - user_id yoksa "default_user" kullanılır (otomatik)
    
    📚 response_model=ChatResponse:
        FastAPI cevabı otomatik ChatResponse formatına göre doğrular ve döker.
        /docs sayfasında ne döneceği de otomatik belgelenir.
    """
    print(f"\n[{request.user_id}]: {request.message}")

    try:
        # history listesini dict listesine çevir (eva_agent beklediği format)
        history_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        eva_response = chat_with_eva(
            user_message=request.message,
            user_id=request.user_id,
            conversation_history=history_dicts
        )

        print(f"Eva: {eva_response[:100]}...")

        return ChatResponse(
            response=eva_response,
            user_id=request.user_id
        )

    except Exception as e:
        print(f"Hata: {str(e)}")
        # 📚 HTTPException: FastAPI'de hata döndürmenin standart yolu
        raise HTTPException(
            status_code=500,
            detail=f"Eva şu an düşünemedi: {str(e)}"
        )


@router.get("/chat/memory-stats", response_model=MemoryStatsResponse)
def memory_stats(user_id: str = "default_user"):
    """
    Hafıza istatistiklerini döner.
    
    📚 Query parametresi (URL'deki ?user_id=...):
        Flask'ta: request.args.get("user_id")
        FastAPI'de: fonksiyon parametresi olarak yaz, otomatik alır!
    
    GET /api/chat/memory-stats?user_id=default_user
    """
    memory = get_memory()
    count = memory.get_memory_count(user_id)

    return MemoryStatsResponse(
        user_id=user_id,
        memory_count=count,
        message=f"Eva'nın hafızasında {count} konuşma kaydı var."
    )
