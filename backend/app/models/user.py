"""
models/user.py - Kullanıcı Veritabanı Modeli
==============================================
SQLAlchemy modeli — Flask-SQLAlchemy olmadan.
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """
    Kullanıcı tablosu.
    İleride auth sistemi eklendiğinde kullanılacak.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<User {self.username}>"
