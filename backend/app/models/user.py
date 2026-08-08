"""
models/user.py - Kullanıcı Veritabanı Modeli
==============================================
Faz 2: Kimlik doğrulama için genişletildi.
email, hashed_password, is_active, last_login eklendi.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """Kullanıcı tablosu — Faz 2 Auth sistemi."""
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String(80), unique=True, nullable=False, index=True)
    email         = Column(String(120), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, server_default=func.now())
    last_login    = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User {self.username}>"
