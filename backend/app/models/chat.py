"""
models/chat.py - Sohbet ve Mesaj Modelleri
==========================================
Faz 3: Konuşma geçmişini MySQL'e kaydetmek için.

Conversation: Her yeni sohbet oturumu (başlık, tarih, user_id)
Message:      O sohbetteki her mesaj (kim yazdı, ne yazdı, ne zaman)
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Conversation(Base):
    """Sohbet oturumu tablosu — her 'Yeni Sohbet' buraya bir satır ekler."""
    __tablename__ = "conversations"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title      = Column(String(200), default="Yeni Sohbet")
    # NULL = Eva sohbeti (sol panel geçmişi). Dolu = karakter/ata sohbeti
    # (Eva listesinde görünmez; karakterin kendi geçmişinde durur).
    ancestor_id = Column(
        Integer,
        ForeignKey("ancestors.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # İlişki: bu sohbetin mesajlarına doğrudan conversation.messages ile erişilebilir
    messages = relationship("Message", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="Message.created_at")
    user     = relationship("User")

    def __repr__(self):
        return f"<Conversation id={self.id} user={self.user_id} title='{self.title}'>"


class Message(Base):
    """Mesaj tablosu — her atılan mesaj buraya kaydedilir."""
    __tablename__ = "messages"

    id              = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    # role: 'user' = kullanıcı yazdı | 'assistant' = Eva yazdı
    role            = Column(Enum("user", "assistant", name="message_role"), nullable=False)
    content         = Column(Text, nullable=False)
    created_at      = Column(DateTime, server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message id={self.id} role={self.role} conv={self.conversation_id}>"
