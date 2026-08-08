"""
core/dependencies.py - FastAPI Bağımlılıkları
==============================================
get_current_user(): Korumalı endpoint'lere giriş için
JWT token'ı doğrular ve kullanıcıyı döndürür.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth import decode_token
from app.models.user import User


# HTTPBearer: "Authorization: Bearer <token>" header'ını otomatik okur
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Korumalı endpoint'lerde kullanılır.

    Nasıl çalışır:
    1. Request header'ından "Authorization: Bearer <token>" alır
    2. Token'ı decode_token() ile doğrular
    3. DB'den kullanıcıyı çeker
    4. Kullanıcıyı endpoint'e hazır verir

    Hata durumları:
    - Token yoksa    → 403 (HTTPBearer otomatik)
    - Token geçersiz → 401
    - Kullanıcı yok  → 401
    - Hesap pasif    → 401
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Oturum süresi dolmuş veya geçersiz. Lütfen tekrar giriş yapın.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    token_data = decode_token(token)

    if token_data is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user
