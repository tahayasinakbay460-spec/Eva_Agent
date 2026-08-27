"""
routes/history.py - Sohbet Geçmişi Endpoint'leri
==================================================
Faz 3: Sol panel (sidebar) için API rotaları.

GET  /api/history/conversations         → Kullanıcının tüm sohbet başlıkları
GET  /api/history/conversations/{id}    → Tek bir sohbetin tüm mesajları
POST /api/history/conversations         → Yeni sohbet oturumu başlat
PATCH  /api/history/conversations/{id}  → Sohbeti yeniden adlandır
DELETE /api/history/conversations/{id} → Sohbeti sil
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.chat import Conversation, Message
from app.schemas.history import (
    ConversationCreate, ConversationRename, ConversationOut, ConversationDetail
)

router = APIRouter()


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kullanıcının tüm sohbetlerini en yeniden eskiye doğru getirir."""
    conversations = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == current_user.id,
            Conversation.ancestor_id.is_(None),
        )
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return conversations


@router.post("/conversations", response_model=ConversationOut) # şimdilik kullanılmıyor
def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Yeni boş bir sohbet oturumu oluşturur."""
    conv = Conversation(user_id=current_user.id, title=body.title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Belirli bir sohbetin tüm mesajlarını getirir."""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,  # Başkasının sohbetine erişimi engelle!
        Conversation.ancestor_id.is_(None),
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı.")

    return conv


@router.patch("/conversations/{conv_id}", response_model=ConversationOut)
def rename_conversation(
    conv_id: int,
    body: ConversationRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sohbet başlığını günceller."""
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Başlık boş olamaz.")
    if len(title) > 200:
        title = title[:200]

    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.ancestor_id.is_(None),
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı.")

    conv.title = title
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bir sohbeti ve içindeki tüm mesajları siler."""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.ancestor_id.is_(None),
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı.")

    db.delete(conv)
    db.commit()
    return {"message": "Sohbet silindi."}
