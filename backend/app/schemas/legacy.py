"""
schemas/legacy.py — Ata Teknolojisi Pydantic Şemaları (Faz 8)
==============================================================
API'ye gelen ve giden verilerin tip ve format doğrulamasını yapar.

📚 Öğretici Not:
    Pydantic modeli = veri kalıpçısı.
    Frontend'den gelen JSON'u otomatik doğrular.
    Eksik veya yanlış tipte veri gelirse 422 hatası döner.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# ATA PROFİLİ ŞEMAları
# ══════════════════════════════════════════════════════════════════════════════

class AncestorCreateRequest(BaseModel):
    """
    POST /api/legacy/ancestors — Yeni ata oluşturma isteği.
    
    Örnek JSON:
    {
        "full_name": "Mehmet Dede",
        "relation_type": "Dede",
        "birth_year": "1940",
        "temperament": "Sakin, bilge, espritüel",
        "backstory": "Köyde büyüdü, İstanbul'a göç etti..."
    }
    """
    full_name: str = Field(..., min_length=2, max_length=200,
                           description="Atanın tam adı")
    relation_type: str = Field(..., min_length=1, max_length=100,
                              description="Kullanıcıyla ilişkisi: Dede, Baba, Anne, Kız Arkadaş, Ben vb.")
    birth_year: Optional[str] = Field(None, max_length=10,
                                      description="Doğum yılı (isteğe bağlı)")
    death_year: Optional[str] = Field(None, max_length=10,
                                      description="Vefat yılı (isteğe bağlı)")
    temperament: Optional[str] = Field(None,
                                       description="Mizaç özellikleri: sakin, espritüel, sert, sevecen vb.")
    backstory: Optional[str] = Field(None,
                                     description="Kısa hayat hikayesi")


class AncestorUpdateRequest(BaseModel):
    """
    PUT /api/legacy/ancestors/{id} — Ata profilini güncelleme isteği.
    Sadece gönderilen alanlar güncellenir (kısmi güncelleme).
    """
    full_name: Optional[str] = Field(None, min_length=2, max_length=200)
    relation_type: Optional[str] = Field(None, min_length=1, max_length=100)
    birth_year: Optional[str] = Field(None, max_length=10)
    death_year: Optional[str] = Field(None, max_length=10)
    temperament: Optional[str] = None
    backstory: Optional[str] = None


class AncestorResponse(BaseModel):
    """
    Ata profili yanıtı — listeleme ve detay gösteriminde kullanılır.
    """
    id: int
    full_name: str
    relation_type: str
    birth_year: Optional[str] = None
    death_year: Optional[str] = None
    temperament: Optional[str] = None
    backstory: Optional[str] = None
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    pdf_url: Optional[str] = None
    is_legacy_import: bool = False
    original_ancestor_id: Optional[int] = None
    is_transferable: bool = False  # Miras alınan karakter başkasına aktarılabilir mi
    memory_count: int = 0          # Bu ataya ait kaç anı var
    has_legacy_key: bool = False   # Miras anahtarı üretilmiş mi
    created_at: Optional[datetime] = None


# ══════════════════════════════════════════════════════════════════════════════
# ANI ŞEMAları
# ══════════════════════════════════════════════════════════════════════════════

class MemoryCreateRequest(BaseModel):
    """
    POST /api/legacy/ancestors/{id}/memories — Yeni anı yükleme isteği.
    
    Örnek JSON:
    {
        "title": "Dedemin köy hikayeleri",
        "content": "Dedem her akşam bize köydeki günlerini anlatırdı...",
        "memory_type": "text"
    }
    """
    title: Optional[str] = Field(None, max_length=300,
                                 description="Anının başlığı")
    content: str = Field(..., min_length=10,
                         description="Anının tam metni (en az 10 karakter)")
    memory_type: str = Field("text",
                             description="Anı türü: text, pdf, story")


class MemoryResponse(BaseModel):
    """
    Anı yanıtı — listeleme ve detayda kullanılır.
    """
    id: int
    title: Optional[str] = None
    content: str
    memory_type: str
    created_at: Optional[datetime] = None


# ══════════════════════════════════════════════════════════════════════════════
# MİRAS ANAHTARI ŞEMAları
# ══════════════════════════════════════════════════════════════════════════════

class LegacyKeyCreateRequest(BaseModel):
    """
    POST /api/legacy/ancestors/{id}/key — Miras anahtarı üretme isteği.
    
    📚 valid_days: Anahtarın kaç gün geçerli olacağı.
        None (boş) gönderilirse anahtar süresiz olur.
        Güvenlik için süreli anahtar önerilir — anahtar yanlış ele geçerse
        süre dolunca kendiliğinden geçersiz hale gelir.
    """
    heir_email: Optional[str] = Field(None,
                                      description="Varisin e-posta adresi (opsiyonel)")
    valid_days: Optional[int] = Field(None, ge=1, le=3650,
                                      description="Anahtar kaç gün geçerli olsun (boş = süresiz)")
    is_transferable: bool = Field(False,
                                  description="Varis, karakteri kendi mirasçısına aktarabilsin mi (izin modeli)")


class LegacyKeyResponse(BaseModel):
    """
    Miras anahtarı yanıtı — anahtar bilgilerini döndürür.
    """
    id: int
    key_hash: str                       # EVA-XXXX-XXXX-XXXX formatında anahtar
    heir_email: Optional[str] = None
    is_active: bool
    ancestor_name: str                  # Hangi atanın anahtarı olduğunu göster
    expires_at: Optional[datetime] = None   # Geçerlilik sonu (None = süresiz)
    is_expired: bool = False                # Süresi dolmuş mu (frontend için hazır bilgi)
    is_transferable: bool = False           # Nesiller arası aktarılabilir mi
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class LegacyKeyEnterRequest(BaseModel):
    """
    POST /api/legacy/enter — Miras anahtarıyla giriş isteği.
    Varis (anahtar sahibi) bu endpoint'i kullanarak atanın
    dijital mirasına erişir.
    """
    legacy_key: str = Field(..., min_length=10,
                            description="Miras anahtarı (EVA-XXXX-XXXX-XXXX formatında)")


class LegacyKeyEnterResponse(BaseModel):
    """
    Miras anahtarıyla giriş yanıtı.
    Varisin sohbet başlatması için gerekli bilgileri döndürür.
    """
    success: bool
    ancestor_id: int
    ancestor_name: str
    relation_type: str
    has_photo: bool                     # Fotoğraf var mı (yoksa Eva isteyecek)
    missing_info: List[str] = []       # Eksik bilgiler listesi
    access_token: str                   # Geçici JWT token (anonim varis erişimi)
    message: str


# ══════════════════════════════════════════════════════════════════════════════
# ATA SOHBET ŞEMAları
# ══════════════════════════════════════════════════════════════════════════════

class LegacyChatRequest(BaseModel):
    """
    POST /api/legacy/chat — Ata persona'sıyla sohbet isteği.
    
    📚 Bu endpoint'e mesaj gönderildiğinde Eva, o atanın kişiliğine
        bürünerek anılarına ve mizacına sadık kalarak cevap verir.
    """
    ancestor_id: int = Field(..., description="Hangi atayla konuşulacak")
    message: str = Field(..., min_length=1, description="Kullanıcının mesajı")
    history: List[dict] = Field(default=[], description="Sohbet geçmişi")
    tracking_id: Optional[str] = Field(default=None, description="Frontend tarafından iptal işlemi için gönderilen benzersiz ID")


class LegacyChatResponse(BaseModel):
    """
    Ata sohbet yanıtı.
    """
    response: str           # Atanın ağzından Eva'nın cevabı
    ancestor_id: int
    ancestor_name: str
    conversation_id: Optional[int] = None


class LegacyChatMessageOut(BaseModel):
    """Karakter sohbetindeki tek mesaj."""
    role: str
    content: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LegacyChatHistoryResponse(BaseModel):
    """
    GET /api/legacy/ancestors/{id}/chat — karakterin kalıcı sohbet geçmişi.
    """
    conversation_id: int
    ancestor_id: int
    ancestor_name: str
    photo_url: Optional[str] = None
    messages: List[LegacyChatMessageOut] = []


# ══════════════════════════════════════════════════════════════════════════════
# DEAD MAN'S SWITCH ŞEMAları
# ══════════════════════════════════════════════════════════════════════════════

class DeadManSwitchCreateRequest(BaseModel):
    """
    POST /api/legacy/deadman — Dead Man's Switch oluşturma isteği.
    
    📚 Kullanıcı belirli bir süre sisteme giriş yapmazsa,
        miras anahtarı otomatik olarak belirtilen e-postaya gönderilir.
    """
    ancestor_id: int = Field(..., description="Hangi atanın mirası gönderilecek")
    legacy_key_id: int = Field(..., description="Hangi anahtar gönderilecek")
    notify_email: str = Field(..., description="Bildirim e-posta adresi")
    inactive_days: int = Field(180, ge=30, le=3650,
                               description="Kaç gün sonra tetiklensin (30-3650)")


class DeadManSwitchResponse(BaseModel):
    """
    Dead Man's Switch yanıtı.
    """
    id: int
    ancestor_name: str
    notify_email: str
    inactive_days: int
    last_checkin: Optional[datetime] = None
    triggered: bool
    created_at: Optional[datetime] = None
