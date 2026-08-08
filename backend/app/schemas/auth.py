"""
schemas/auth.py - Kimlik Doğrulama Şemaları (Pydantic)
========================================================
Kayıt, giriş ve token yanıtları için veri doğrulama.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class RegisterRequest(BaseModel):
    """POST /api/auth/register için beklenen veri."""
    username: str = Field(..., min_length=3, max_length=30,
                          description="Kullanıcı adı (3-30 karakter)")
    email: EmailStr = Field(..., description="Geçerli bir e-posta adresi")
    password: str = Field(..., min_length=8,
                          description="Şifre (en az 8 karakter)")


class LoginRequest(BaseModel):
    """POST /api/auth/login için beklenen veri."""
    email: EmailStr = Field(..., description="Kayıtlı e-posta") # Field ekstra sartlandırmalar icindir.
    password: str = Field(..., description="Şifre")


class TokenResponse(BaseModel):
    """Başarılı giriş/kayıt sonrası döndürülen yanıt."""
    access_token: str   # JWT token — frontend localStorage'a kaydedecek
    token_type: str     # "bearer"
    user_id: int
    username: str


class TokenData(BaseModel):
    """JWT payload içindeki veri."""
    user_id: Optional[int] = None


class UserMeResponse(BaseModel):
    """GET /api/auth/me yanıtı."""
    user_id: int
    username: str
    email: str
