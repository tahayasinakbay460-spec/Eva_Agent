"""
routes/auth.py - Kimlik Doğrulama Endpoint'leri
================================================
POST /api/auth/register  → Yeni kullanıcı kaydı
POST /api/auth/login     → Giriş yap, token al
GET  /api/auth/me        → Mevcut kullanıcı bilgileri
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest, LoginRequest,
    TokenResponse, UserMeResponse
)
from app.core.auth import hash_password, verify_password, create_access_token
from app.core.dependencies import get_current_user


router = APIRouter()


# ─── Kayıt ──────────────────────────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse,# response_model defaulttur sadece frontende bilgi verir.
             status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)): # depens veri tabanı baglnatısı olsuturur 
    # ilk basta sonra onu otomaik de kapatabilir. sonra da register fonkiyonu calısır 
    # request burda default degil ama fonksiyon ilk calısmdan once pydantic calsıyor (dekorator sayesinde)
    """ 
    Yeni kullanıcı kaydı.

    Adımlar:
    1. E-posta ve kullanıcı adı benzersiz mi? → değilse 400
    2. Şifreyi bcrypt ile hashle
    3. DB'ye kaydet
    4. JWT token oluştur ve döndür (kayıt = otomatik giriş)
    """
    # E-posta çakışma kontrolü
    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(
            status_code=400,
            detail="Bu e-posta adresi zaten kayıtlı."
        )

    # Kullanıcı adı çakışma kontrolü
    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(
            status_code=400,
            detail="Bu kullanıcı adı zaten alınmış."
        )

    # Kullanıcı oluştur
    new_user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    print(f"[AUTH] Yeni kullanıcı: {new_user.username} ({new_user.email})")

    token = create_access_token(user_id=new_user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=new_user.id,
        username=new_user.username
    )


# ─── Giriş ──────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Kullanıcı girişi.

    Adımlar:
    1. E-posta ile kullanıcıyı bul
    2. Hesap aktif mi?
    3. Şifreyi doğrula
    4. last_login güncelle
    5. JWT token döndür
    """
    user = db.query(User).filter(User.email == request.email).first()

    # Kullanıcı yok veya şifre yanlış → aynı mesaj (güvenlik: hangisi yanlış belli olmasın)
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Hesabınız devre dışı bırakılmış."
        )

    # Son giriş zamanını güncelle
    user.last_login = datetime.utcnow()
    db.commit()

    print(f"[AUTH] Giriş: {user.username}")

    token = create_access_token(user_id=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username
    )


# ─── Mevcut Kullanıcı ───────────────────────────────────────────────────────
@router.get("/me", response_model=UserMeResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Token geçerliyse mevcut kullanıcı bilgilerini döndürür.
    Frontend sayfa yenilenince bu endpoint ile token'ı doğrular.
    """
    return UserMeResponse(
        user_id=current_user.id,
        username=current_user.username,
        email=current_user.email
    )
