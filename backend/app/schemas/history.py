"""
schemas/history.py - Sohbet Geçmişi Şemaları
==============================================
Faz 3: Geçmiş panel için veri yapıları.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    """Yeni sohbet başlatmak için."""
    title: Optional[str] = "Yeni Sohbet"


class MessageOut(BaseModel):
    """Tek bir mesajı frontend'e döndürmek için."""
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    """Sohbet listesinde gösterilecek özet bilgi."""
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationDetail(BaseModel):
    """Tıklanan eski sohbetin tam içeriği (tüm mesajlar)."""
    id: int
    title: str
    created_at: datetime
    messages: List[MessageOut]

    class Config:
        from_attributes = True
