"""
schemas/chat.py - API Veri Şemaları (Pydantic)
================================================
Pydantic modelleri, gelen ve giden verilerin
tipini ve formatını otomatik olarak doğrular.

📚 Örnek:
    Kullanıcı { "message": 123 } gönderirse
    Pydantic bunu otomatik string'e çevirir.
    Zorunlu alan eksikse 422 hatası döner.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class HistoryMessage(BaseModel):
    """Tek bir konuşma geçmişi mesajı"""
    role: str           # "user" veya "assistant"
    content: str        # Mesajın içeriği


class ChatRequest(BaseModel):
    """
    POST /api/chat için beklenen JSON body.
    
    Örnek:
    {
        "message": "Merhaba Eva!",
        "user_id": "kullanici_123",
        "history": [...]
    }
    """
    message: str = Field(..., min_length=1, description="Kullanıcının mesajı")
    history: List[HistoryMessage] = Field(default=[], description="Oturum geçmişi")
    conversation_id: Optional[int] = Field(default=None, description="Aktif sohbet ID'si (yoksa yeni oluşturulur)")
    detected_emotion: Optional[str] = Field(default=None, description="Kameradan tespit edilen duygu (Faz 5)")


class ChatResponse(BaseModel):
    """
    POST /api/chat'in döndürdüğü JSON.
    
    Örnek:
    {
        "response": "Merhaba! Ben Eva...",
        "user_id": "kullanici_123"
    }
    """
    response: str
    user_id: str
    conversation_id: int


class MemoryStatsResponse(BaseModel):
    """GET /api/chat/memory-stats'ın döndürdüğü JSON."""
    user_id: str
    memory_count: int
    message: str


class HealthResponse(BaseModel):
    """GET /api/health'in döndürdüğü JSON."""
    status: str
    message: str
