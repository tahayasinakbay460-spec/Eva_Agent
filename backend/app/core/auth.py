"""
core/auth.py - Kimlik Doğrulama İş Mantığı
============================================
Şifre hashleme (bcrypt doğrudan) + JWT token işlemleri.
"""
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.config import Config
from app.schemas.auth import TokenData


# ─── Bcrypt Şifre Hashleme ──────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Düz metin şifreyi bcrypt ile hashle.
    Örn: "12345678" → "$2b$12$xxx..." (geri döndürülemez)
    """
    salt = bcrypt.gensalt(rounds=12) # ekstradan rastgele karakterler ekler 
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt) # once sifreyi byta cevirip hashler 
    return hashed.decode("utf-8") # sonra da string olarak dondurur decode eder.


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Kullanıcının girdiği şifre, DB'deki hash ile eşleşiyor mu?
    bcrypt timing-safe karşılaştırma yapar.
    """
    return bcrypt.checkpw( # default fonkyiondur once gidip saltı alır sonra kendine gore hashler
        plain_password.encode("utf-8"), # girilen sifreyi byte cevirir
        hashed_password.encode("utf-8") # hashlenmis sifreyi byte cevirir
    )


# ─── JWT Token ──────────────────────────────────────────────────────────────
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7  # Token 7 gün geçerli


def create_access_token(user_id: int) -> str:
    """
    Kullanıcı ID'si ile JWT token oluştur.
    Token payload: { "sub": "42", "exp": <timestamp> }
    """
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS) # suresi dolacak zaman
    payload = {
        "sub": str(user_id),
        "exp": expire
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[TokenData]:
    """
    JWT token'ı çöz ve TokenData döndür.
    Token geçersizse veya süresi dolmuşsa None döner.
    """
    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=[ALGORITHM]) # tokeni cozer ve payloadu dondurur eger token basarısız olursa hata verir 
        user_id_str: str = payload.get("sub") # token icindeki user id yi alir
        if user_id_str is None: # eger user id yoksa hata verir 
            return None
        return TokenData(user_id=int(user_id_str)) # token icindeki user idyi dondurur 
    except JWTError:
        return None
