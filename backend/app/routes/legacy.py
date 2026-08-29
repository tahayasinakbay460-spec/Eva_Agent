"""
routes/legacy.py — Ata Teknolojisi API Endpoint'leri (Faz 8)
=============================================================
Dijital Miras sisteminin tüm REST API rotaları.

Endpoint Listesi:
    GET    /api/legacy/ancestors              → Tüm ataları listele
    POST   /api/legacy/ancestors              → Yeni ata oluştur
    GET    /api/legacy/ancestors/{id}         → Tek ata detayı
    PUT    /api/legacy/ancestors/{id}         → Ata güncelle
    DELETE /api/legacy/ancestors/{id}         → Ata sil
    POST   /api/legacy/ancestors/{id}/memories → Anı yükle
    GET    /api/legacy/ancestors/{id}/memories  → Anıları listele
    POST   /api/legacy/ancestors/{id}/key     → Miras anahtarı üret
    GET    /api/legacy/ancestors/{id}/key     → Mevcut anahtarı göster
    GET    /api/legacy/ancestors/{id}/chat    → Karakter sohbet geçmişi
    POST   /api/legacy/chat                   → Ata persona sohbeti
    POST   /api/legacy/enter                  → Miras anahtarıyla giriş
    POST   /api/legacy/deadman                → Dead Man's Switch ayarla
    GET    /api/legacy/deadman                → Switch'leri listele
    POST   /api/legacy/deadman/checkin        → Check-in (ben buradayım)
"""

import os
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.legacy import Ancestor, AncestorMemory, LegacyKey, DeadManSwitch
from app.models.chat import Conversation, Message
from app.schemas.legacy import (
    AncestorCreateRequest, AncestorUpdateRequest, AncestorResponse,
    MemoryCreateRequest, MemoryResponse,
    LegacyKeyCreateRequest, LegacyKeyResponse,
    LegacyKeyEnterRequest, LegacyKeyEnterResponse,
    LegacyChatRequest, LegacyChatResponse,
    LegacyChatHistoryResponse, LegacyChatMessageOut,
    DeadManSwitchCreateRequest, DeadManSwitchResponse
)
from app.routes.chat import CANCELLED_REQUESTS
from app.core.dependencies import get_current_user
from app.core.legacy_memory import get_legacy_memory
from app.core.legacy_chat import chat_as_ancestor
from app.core.auth import create_access_token


# FastAPI router — prefix /api/legacy main.py'de eklenir
router = APIRouter()

# ─── Yükleme Klasörü ─────────────────────────────────────────────────────────
# 📚 Mutlak yol kullanıyoruz: göreli "uploads/" yolu, sunucunun hangi klasörden
#    başlatıldığına göre değişir ve dosyalar yanlış yere kaydedilebilirdi.
#    Bu yol her zaman backend/uploads klasörünü gösterir (main.py'deki mount ile aynı).
UPLOADS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
)


# ══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════════════

def _save_upload(file: Optional[UploadFile], subfolder: str) -> Optional[str]:
    """
    Yüklenen dosyayı diske kaydet ve erişim URL'ini döndür.
    
    📚 Akış:
        1. Dosya backend/uploads/legacy/{subfolder}/ altına benzersiz isimle yazılır
        2. "/api/uploads/legacy/{subfolder}/{dosya}" URL'i döndürülür
        3. Bu URL, main.py'deki StaticFiles mount'u sayesinde tarayıcıdan erişilebilir
    
    Args:
        file: Frontend'den gelen dosya (None olabilir)
        subfolder: Alt klasör adı (photos, audios, videos, pdfs)
        
    Returns:
        Erişim URL'i veya None (dosya yoksa)
    """
    if not file or not file.filename:
        return None
    upload_dir = os.path.join(UPLOADS_DIR, "legacy", subfolder)
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return f"/api/uploads/legacy/{subfolder}/{filename}"


def _is_key_expired(key: LegacyKey) -> bool:
    """
    Anahtarın süresi dolmuş mu kontrol et.
    
    📚 expires_at = None ise anahtar süresizdir, asla dolmaz.
    """
    return key.expires_at is not None and key.expires_at < datetime.utcnow()


def _key_to_response(key: LegacyKey, ancestor_name: str) -> LegacyKeyResponse:
    """
    SQLAlchemy LegacyKey nesnesini Pydantic LegacyKeyResponse'a çevir.
    """
    return LegacyKeyResponse(
        id=key.id,
        key_hash=key.key_hash,
        heir_email=key.heir_email,
        is_active=key.is_active,
        ancestor_name=ancestor_name,
        expires_at=key.expires_at,
        is_expired=_is_key_expired(key),
        is_transferable=bool(key.is_transferable),
        created_at=key.created_at,
        last_used_at=key.last_used_at
    )


def _generate_legacy_key() -> str:
    """
    Benzersiz miras anahtarı üret.
    
    📚 Format: EVA-XXXX-XXXX-XXXX
        UUID'den türetilir, kısa ve okunabilir.
        Kullanıcı bunu kopyalayıp varisine verir.
    
    Returns:
        "EVA-A1B2-C3D4-E5F6" formatında benzersiz anahtar
    """
    # UUID'den 12 karakterlik hex üret
    raw = uuid.uuid4().hex[:12].upper()
    # EVA-XXXX-XXXX-XXXX formatına dönüştür
    return f"EVA-{raw[:4]}-{raw[4:8]}-{raw[8:12]}"


def _ancestor_to_response(ancestor: Ancestor) -> AncestorResponse:
    """
    SQLAlchemy Ancestor nesnesini Pydantic AncestorResponse'a çevir.
    
    📚 ORM nesneleri doğrudan JSON'a döndürülemez.
        Pydantic modeli ile sarmalayarak güvenli serileştirme yaparız.
    
    Args:
        ancestor: Veritabanından gelen Ancestor ORM nesnesi
        
    Returns:
        AncestorResponse Pydantic modeli
    """
    return AncestorResponse(
        id=ancestor.id,
        full_name=ancestor.full_name,
        relation_type=ancestor.relation_type,
        birth_year=ancestor.birth_year,
        death_year=ancestor.death_year,
        temperament=ancestor.temperament,
        backstory=ancestor.backstory,
        photo_url=ancestor.photo_url,
        audio_url=ancestor.audio_url,
        video_url=ancestor.video_url,
        pdf_url=ancestor.pdf_url,
        is_legacy_import=bool(ancestor.is_legacy_import),
        original_ancestor_id=ancestor.original_ancestor_id,
        is_transferable=bool(ancestor.is_transferable),
        memory_count=len(ancestor.memories) if ancestor.memories else 0,
        has_legacy_key=any(k.is_active for k in ancestor.legacy_keys) if ancestor.legacy_keys else False,
        created_at=ancestor.created_at
    )


def _get_ancestor_missing_info(ancestor: Ancestor) -> list:
    """
    Atanın profilinde eksik bilgileri tespit et.
    
    📚 Miras anahtarıyla giren varis için kullanılır.
        Eksik bilgiler varsa Eva bunları isteyecek.
    
    Args:
        ancestor: Veritabanından gelen Ancestor nesnesi
        
    Returns:
        Eksik bilgi isimleri listesi (ör: ["fotoğraf", "anılar"])
    """
    missing = []
    if not ancestor.photo_url:
        missing.append("fotoğraf")
    if not ancestor.temperament:
        missing.append("mizaç bilgisi")
    if not ancestor.backstory:
        missing.append("hayat hikayesi")
    if not ancestor.memories or len(ancestor.memories) == 0:
        missing.append("anılar")
    return missing


def _get_or_create_legacy_conversation(
    db: Session,
    user_id: int,
    ancestor: Ancestor,
) -> Conversation:
    """
    Bu kullanıcı + karakter çifti için tek bir kalıcı sohbet döndürür.
    Eva sohbetlerinden ancestor_id ile ayrılır.
    """
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user_id,
            Conversation.ancestor_id == ancestor.id,
        )
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if conv:
        return conv

    conv = Conversation(
        user_id=user_id,
        ancestor_id=ancestor.id,
        title=ancestor.full_name,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


# ══════════════════════════════════════════════════════════════════════════════
# MASTER PERSONA (KENDİ MİRASIM)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/master")
def get_master_persona(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kullanıcının kendi 'Master Persona'sını getirir."""
    master = db.query(Ancestor).filter(
        Ancestor.user_id == current_user.id,
        Ancestor.relation_type == "MASTER_PERSONA"
    ).first()
    
    if not master:
        return {"has_master": False}
    
    # 📚 Otomatik onarım: Eski sürümde master persona jenerik "Benim Mirasım"
    #    adıyla oluşturuluyordu ve persona kendi adını bu sanıyordu.
    #    Burada gerçek kullanıcı adıyla değiştirilir (tek seferlik düzeltme).
    if master.full_name in ("Benim Mirasım", "Benim Miras"):
        master.full_name = current_user.username
        db.commit()
        db.refresh(master)
        
    return {
        "has_master": True,
        "ancestor": _ancestor_to_response(master)
    }

@router.post("/master")
def create_master_persona(
    full_name: str = Form(...),
    birth_year: Optional[str] = Form(None),
    temperament: Optional[str] = Form(None),
    backstory: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kullanıcının kendi 'Master Persona'sını oluşturur."""
    existing = db.query(Ancestor).filter(
        Ancestor.user_id == current_user.id,
        Ancestor.relation_type == "MASTER_PERSONA"
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Zaten bir Master Personanız var.")

    photo_path = _save_upload(photo, "photos")
    
    # 📚 Jenerik isim gönderilirse gerçek kullanıcı adını kullan —
    #    persona kendi adını "Benim Mirasım" sanmasın.
    if not full_name or full_name.strip() in ("Benim Mirasım", "Benim Miras"):
        full_name = current_user.username
    
    master = Ancestor(
        user_id=current_user.id,
        full_name=full_name,
        birth_year=birth_year,
        relation_type="MASTER_PERSONA",
        temperament=temperament,
        backstory=backstory,
        photo_url=photo_path
    )
    db.add(master)
    db.commit()
    db.refresh(master)
    
    return _ancestor_to_response(master)

# ══════════════════════════════════════════════════════════════════════════════
# ATA PROFİLLERİ (CRUD)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/ancestors", response_model=list[AncestorResponse])
def list_ancestors(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kullanıcının tüm ata profillerini listele.
    
    📚 JWT korumalı — sadece giriş yapmış kullanıcı kendi atalarını görür.
        MASTER_PERSONA hariç tutulur: o, "Güvenlik Ayarları" bölümünde yönetilir,
        normal karakter listesinde görünmemeli.
    """
    ancestors = db.query(Ancestor).filter(
        Ancestor.user_id == current_user.id,
        Ancestor.relation_type != "MASTER_PERSONA"
    ).order_by(Ancestor.created_at.desc()).all()
    
    return [_ancestor_to_response(a) for a in ancestors]


@router.post("/ancestors", response_model=AncestorResponse, status_code=201)
def create_ancestor(
    full_name: str = Form(...),
    relation_type: str = Form(...),
    birth_year: Optional[str] = Form(None),
    death_year: Optional[str] = Form(None),
    temperament: Optional[str] = Form(None),
    backstory: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
    pdf: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Yeni bir ata profili oluştur (Medya destekli).
    """
    # Aynı isimde ata var mı kontrolü
    existing = db.query(Ancestor).filter(
        Ancestor.user_id == current_user.id,
        Ancestor.full_name == full_name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"'{full_name}' adında bir kişi zaten mevcut. Lütfen farklı bir isim kullanın."
        )

    photo_url = _save_upload(photo, "photos")
    audio_url = _save_upload(audio, "audios")
    video_url = _save_upload(video, "videos")
    pdf_url = _save_upload(pdf, "pdfs")
    
    new_ancestor = Ancestor(
        user_id=current_user.id,
        full_name=full_name,
        relation_type=relation_type,
        birth_year=birth_year,
        death_year=death_year,
        temperament=temperament,
        backstory=backstory,
        photo_url=photo_url,
        audio_url=audio_url,
        video_url=video_url,
        pdf_url=pdf_url
    )
    
    db.add(new_ancestor)
    db.commit()
    db.refresh(new_ancestor)
    
    print(f"[ATA] Yeni ata olusturuldu: {new_ancestor.full_name} ({new_ancestor.relation_type}) -- Sahip: {current_user.username}")
    return _ancestor_to_response(new_ancestor)


@router.get("/ancestors/{ancestor_id}", response_model=AncestorResponse)
def get_ancestor(
    ancestor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Tek bir atanın detay bilgilerini getir.
    
    📚 Sadece kullanıcının kendi ataları erişilebilir (güvenlik).
    """
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")
    
    return _ancestor_to_response(ancestor)


@router.put("/ancestors/{ancestor_id}", response_model=AncestorResponse)
def update_ancestor(
    ancestor_id: int,
    full_name: Optional[str] = Form(None),
    relation_type: Optional[str] = Form(None),
    birth_year: Optional[str] = Form(None),
    death_year: Optional[str] = Form(None),
    temperament: Optional[str] = Form(None),
    backstory: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
    pdf: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ata profilini güncelle (kısmi güncelleme, Medya destekli).
    """
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")

    if full_name is not None: ancestor.full_name = full_name
    if relation_type is not None: ancestor.relation_type = relation_type
    if birth_year is not None: ancestor.birth_year = birth_year
    if death_year is not None: ancestor.death_year = death_year
    if temperament is not None: ancestor.temperament = temperament
    if backstory is not None: ancestor.backstory = backstory
    
    photo_url = _save_upload(photo, "photos")
    if photo_url: ancestor.photo_url = photo_url
    
    audio_url = _save_upload(audio, "audios")
    if audio_url: ancestor.audio_url = audio_url
    
    video_url = _save_upload(video, "videos")
    if video_url: ancestor.video_url = video_url
    
    pdf_url = _save_upload(pdf, "pdfs")
    if pdf_url: ancestor.pdf_url = pdf_url
    
    db.commit()
    db.refresh(ancestor)
    
    print(f"[ATA] Ata guncellendi: {ancestor.full_name}")
    
    return _ancestor_to_response(ancestor)


@router.delete("/ancestors/{ancestor_id}", status_code=200)
def delete_ancestor(
    ancestor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ata profilini ve tüm ilişkili verileri sil.
    
    📚 Silme işlemi şunları da siler:
        - Atanın tüm anıları (MySQL + ChromaDB)
        - Atanın tüm miras anahtarları
        - Atanın Dead Man's Switch'leri
    """
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")
    
    # ChromaDB'deki anıları da sil
    legacy_memory = get_legacy_memory()
    legacy_memory.delete_ancestor_memories(ancestor_id)

    # Bu karaktere ait kalıcı sohbetleri sil (Eva geçmişine karışmasın)
    character_chats = db.query(Conversation).filter(
        Conversation.ancestor_id == ancestor_id,
        Conversation.user_id == current_user.id,
    ).all()
    for conv in character_chats:
        db.delete(conv)
    
    # MySQL'den sil (cascade ile anılar, anahtarlar, switch'ler de silinir)
    ancestor_name = ancestor.full_name
    db.delete(ancestor)
    db.commit()
    
    print(f"[ATA] Ata silindi: {ancestor_name}")
    
    return {"message": f"{ancestor_name} profili ve tüm verileri silindi."}


# ══════════════════════════════════════════════════════════════════════════════
# ANI YÖNETİMİ
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/ancestors/{ancestor_id}/memories", response_model=MemoryResponse, status_code=201)
def add_memory(
    ancestor_id: int,
    request: MemoryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ataya yeni bir anı ekle (metin).
    
    📚 Gelen metin hem MySQL'e hem ChromaDB'ye kaydedilir.
        MySQL: Kalıcı depolama ve listeleme için
        ChromaDB: Vektör araması (RAG) için
    
    Adımlar:
        1. Atanın sahibi bu kullanıcı mı kontrol et
        2. ChromaDB'ye vektör olarak kaydet → chroma_doc_id al
        3. MySQL'e anıyı kaydet (chroma_doc_id referansıyla)
    """
    # Ata bu kullanıcıya mı ait?
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")
    
    # ChromaDB'ye kaydet (vektör araması için)
    legacy_memory = get_legacy_memory()
    chroma_doc_id = legacy_memory.save_memory(
        ancestor_id=ancestor_id,
        content=request.content,
        title=request.title
    )
    
    # MySQL'e kaydet (kalıcı depolama)
    new_memory = AncestorMemory(
        ancestor_id=ancestor_id,
        memory_type=request.memory_type,
        title=request.title,
        content=request.content,
        chroma_doc_id=chroma_doc_id
    )
    
    db.add(new_memory)
    db.commit()
    db.refresh(new_memory)
    
    print(f"[ATA] Ani eklendi -> {ancestor.full_name}: \"{request.title or 'Basliksiz'}\"")
    
    return MemoryResponse(
        id=new_memory.id,
        title=new_memory.title,
        content=new_memory.content,
        memory_type=new_memory.memory_type,
        created_at=new_memory.created_at
    )


@router.get("/ancestors/{ancestor_id}/memories", response_model=list[MemoryResponse])
def list_memories(
    ancestor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Atanın tüm anılarını listele.
    """
    # Ata bu kullanıcıya mı ait?
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")
    
    return [
        MemoryResponse(
            id=m.id,
            title=m.title,
            content=m.content,
            memory_type=m.memory_type,
            created_at=m.created_at
        )
        for m in ancestor.memories
    ]


# ══════════════════════════════════════════════════════════════════════════════
# MİRAS ANAHTARI
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/ancestors/{ancestor_id}/key", response_model=LegacyKeyResponse, status_code=201)
def create_legacy_key(
    ancestor_id: int,
    request: LegacyKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ata için miras anahtarı üret.
    
    📚 Her çağrıda yeni bir anahtar üretilir.
        Önceki anahtar(lar) aktif kalmaya devam eder.
        Kullanıcı isterse eski anahtarları devre dışı bırakabilir.
    
    📚 Güvenlik — Geçerlilik Süresi (valid_days):
        Kullanıcı anahtarın kaç gün geçerli olacağını seçebilir.
        Süre dolunca anahtar otomatik geçersizleşir (giriş reddedilir).
        valid_days gönderilmezse anahtar süresiz olur.
    """
    # Ata bu kullanıcıya mı ait?
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")
    
    # 📚 İZİN MODELİ — Güvenlik kontrolü:
    #    Miras alınan (import) bir karakter için anahtar üretme yetkisi,
    #    orijinal sahibin verdiği izne bağlıdır. Anahtar üretilirken
    #    "aktarılabilir" seçilmediyse varis zinciri devam ettiremez.
    #    Frontend sekmeyi gizlese bile API seviyesinde de engellenir.
    if ancestor.is_legacy_import and not ancestor.is_transferable:
        raise HTTPException(
            status_code=403,
            detail="Bu miras karakteri 'tek kişiye özel' olarak paylaşılmış. "
                   "Orijinal sahibi aktarım izni vermediği için yeni anahtar üretemezsiniz."
        )
    
    # Benzersiz anahtar üret
    key_hash = _generate_legacy_key()
    
    # Geçerlilik süresi hesapla (istenirse)
    expires_at = None
    if request.valid_days:
        expires_at = datetime.utcnow() + timedelta(days=request.valid_days)
    
    # Veritabanına kaydet
    new_key = LegacyKey(
        ancestor_id=ancestor_id,
        created_by_user_id=current_user.id,
        key_hash=key_hash,
        heir_email=request.heir_email,
        is_active=True,
        expires_at=expires_at,
        is_transferable=request.is_transferable
    )
    
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    
    validity = f"{request.valid_days} gün geçerli" if request.valid_days else "süresiz"
    print(f"[KEY] Miras anahtari uretildi: {key_hash} -> {ancestor.full_name} ({validity})")
    
    return _key_to_response(new_key, ancestor.full_name)


@router.get("/ancestors/{ancestor_id}/key", response_model=list[LegacyKeyResponse])
def get_legacy_keys(
    ancestor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Atanın miras anahtarlarını listele.
    """
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")
    
    return [_key_to_response(k, ancestor.full_name) for k in ancestor.legacy_keys]


# ══════════════════════════════════════════════════════════════════════════════
# MİRAS ANAHTARIYLA GİRİŞ (VARİS)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/enter", response_model=LegacyKeyEnterResponse)
def enter_with_legacy_key(
    request: LegacyKeyEnterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Miras anahtarıyla giriş yap (varis erişimi).
    
    📚 Anahtar girildiğinde, o anahtara ait karakterin
        bir kopyası (Miras), giren kullanıcının hesabına eklenir.
    """
    # Anahtarı bul
    legacy_key = db.query(LegacyKey).filter(
        LegacyKey.key_hash == request.legacy_key,
        LegacyKey.is_active == True
    ).first()
    
    if not legacy_key:
        raise HTTPException(
            status_code=404,
            detail="Geçersiz veya devre dışı miras anahtarı."
        )
    
    # Anahtarın süresi dolmuş mu? (Güvenlik: süreli anahtarlar otomatik geçersizleşir)
    if _is_key_expired(legacy_key):
        raise HTTPException(
            status_code=403,
            detail="Bu miras anahtarının geçerlilik süresi dolmuş. "
                   "Anahtar sahibinden yeni bir anahtar isteyin."
        )
    
    # Atanın bilgilerini getir
    original_ancestor = db.query(Ancestor).filter(
        Ancestor.id == legacy_key.ancestor_id
    ).first()
    
    if not original_ancestor:
        raise HTTPException(status_code=404, detail="Bu anahtara bağlı profil bulunamadı.")
        
    # Kendi kendine eklemeye çalışıyorsa engelle
    if original_ancestor.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Kendi oluşturduğunuz miras anahtarını kendinize ekleyemezsiniz.")
        
    # Zaten eklenmiş mi kontrol et
    already_imported = db.query(Ancestor).filter(
        Ancestor.user_id == current_user.id,
        Ancestor.original_ancestor_id == original_ancestor.id
    ).first()
    
    if already_imported:
        raise HTTPException(status_code=400, detail="Bu miras profili zaten karakterlerinize eklenmiş.")
    
    # Atayı klonla
    # 📚 Master persona klonlanıyorsa: jenerik "Benim Mirasım" adı yerine
    #    anahtar sahibinin gerçek kullanıcı adını kullan. Varis, karakter
    #    listesinde kimin mirası olduğunu görebilmeli.
    clone_name = original_ancestor.full_name
    if original_ancestor.relation_type == "MASTER_PERSONA":
        if clone_name in ("Benim Mirasım", "Benim Miras", ""):
            owner = db.query(User).filter(User.id == original_ancestor.user_id).first()
            if owner:
                clone_name = owner.username
    
    cloned_ancestor = Ancestor(
        user_id=current_user.id,
        full_name=clone_name,
        relation_type="Miras Bırakan",  # Özel miras etiketi
        birth_year=original_ancestor.birth_year,
        death_year=original_ancestor.death_year,
        temperament=original_ancestor.temperament,
        backstory=original_ancestor.backstory,
        photo_url=original_ancestor.photo_url,
        audio_url=original_ancestor.audio_url,
        video_url=original_ancestor.video_url,
        pdf_url=original_ancestor.pdf_url,
        is_legacy_import=True,
        original_ancestor_id=original_ancestor.id,
        # İzin modeli: anahtar "aktarılabilir" üretildiyse varis de
        # bu karakteri kendi mirasçısına aktarabilir
        is_transferable=bool(legacy_key.is_transferable)
    )
    db.add(cloned_ancestor)
    
    # Son kullanım zamanını güncelle
    legacy_key.last_used_at = datetime.utcnow()
    db.commit()
    db.refresh(cloned_ancestor)
    
    # Anıları da klonla (hem MySQL hem ChromaDB)
    # 📚 ÖNEMLİ: ChromaDB koleksiyonları ata ID'sine göre ayrılır
    #    (legacy_ancestor_{id}). Klonun ID'si farklı olduğu için anıları
    #    yeni koleksiyona da kaydetmek ZORUNDAYIZ — yoksa varis sohbetinde
    #    RAG araması boş döner ve ata anılarını "hatırlayamaz".
    legacy_memory = get_legacy_memory()
    for mem in original_ancestor.memories:
        # Önce ChromaDB'ye kaydet → klona ait yeni vektör ID'si al
        new_chroma_id = legacy_memory.save_memory(
            ancestor_id=cloned_ancestor.id,
            content=mem.content,
            title=mem.title
        )
        cloned_mem = AncestorMemory(
            ancestor_id=cloned_ancestor.id,
            memory_type=mem.memory_type,
            title=mem.title,
            content=mem.content,
            chroma_doc_id=new_chroma_id
        )
        db.add(cloned_mem)
    db.commit()
    
    # Eksik bilgileri tespit et
    missing_info = _get_ancestor_missing_info(cloned_ancestor)
    
    # JWT artık gerekmiyor çünkü kendi hesabında
    access_token = create_access_token(user_id=current_user.id)
    
    print(f"[KEY] Miras profili ice aktarildi: {legacy_key.key_hash} -> {cloned_ancestor.full_name} to User {current_user.username}")
    
    return LegacyKeyEnterResponse(
        success=True,
        ancestor_id=cloned_ancestor.id,
        ancestor_name=cloned_ancestor.full_name,
        relation_type=cloned_ancestor.relation_type,
        has_photo=bool(cloned_ancestor.photo_url),
        missing_info=missing_info,
        access_token=access_token,
        message=f"{cloned_ancestor.full_name} profili karakterlerinize miras olarak eklendi."
    )


# ══════════════════════════════════════════════════════════════════════════════
# ATA PERSONA SOHBET
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/ancestors/{ancestor_id}/chat", response_model=LegacyChatHistoryResponse)
def get_legacy_chat_history(
    ancestor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bu karakterle yapılan kalıcı sohbeti getirir (yoksa boş oluşturur).
    Eva sohbet geçmişinden ayrı tutulur.
    """
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")

    conv = _get_or_create_legacy_conversation(db, current_user.id, ancestor)
    messages = [
        LegacyChatMessageOut(role=m.role, content=m.content, created_at=m.created_at)
        for m in (conv.messages or [])
    ]
    display_name = ancestor.full_name
    if ancestor.relation_type == "MASTER_PERSONA" and display_name in ("Benim Mirasım", "Benim Miras", ""):
        display_name = current_user.username

    return LegacyChatHistoryResponse(
        conversation_id=conv.id,
        ancestor_id=ancestor.id,
        ancestor_name=display_name,
        photo_url=ancestor.photo_url,
        messages=messages,
    )


@router.post("/chat", response_model=LegacyChatResponse)
def legacy_chat(
    request: LegacyChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ata persona'sıyla sohbet et.
    
    📚 Eva, belirtilen atanın kişiliğine bürünerek cevap verir.
        ChromaDB'deki anılar RAG ile sorgulanır ve prompt'a eklenir.
    
    📚 Güvenlik: Sadece atanın SAHİBİ sohbet edebilir.
        Varis de miras anahtarıyla giriş yaptığında profil kendi hesabına
        klonlandığı için, kendi klonunun sahibi olur ve sohbet edebilir.
        Sahiplik kontrolü olmadan herkes herhangi bir ancestor_id ile
        başkalarının atalarıyla konuşabilirdi!
    """
    # Atayı bul — sahibi bu kullanıcı olmalı (güvenlik kontrolü)
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == request.ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")

    conv = _get_or_create_legacy_conversation(db, current_user.id, ancestor)
    db_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in db_messages[-20:]]
    if not history and request.history:
        history = request.history[-20:]
    
    # ─── Master Persona Tespiti ──────────────────────────────────────────────
    # 📚 İki durumda bu sohbet bir "master persona" (kullanıcının kendi dijital
    #    mirası) sohbetidir:
    #    1. Kullanıcı kendi master persona'sıyla konuşuyor
    #    2. Varis, miras anahtarıyla içe aktarılmış bir master klonuyla konuşuyor
    #    Her iki durumda da kişilik EVA'nın ana sohbet hafızasında saklıdır —
    #    o hafızanın sahibini (orijinal kullanıcıyı) bulup chat motoruna geçiririz.
    master_owner = None
    if ancestor.relation_type == "MASTER_PERSONA":
        master_owner = db.query(User).filter(User.id == ancestor.user_id).first()
    elif ancestor.is_legacy_import and ancestor.original_ancestor_id:
        # 📚 Zinciri köke kadar takip et: miras alınan karakter tekrar miras
        #    bırakılabilir (dede → baba → torun). Klonun klonunda da kök
        #    master persona'ya ulaşabilmeliyiz. max 10 adım = döngü koruması.
        root = ancestor
        for _ in range(10):
            if not root.original_ancestor_id:
                break
            parent = db.query(Ancestor).filter(
                Ancestor.id == root.original_ancestor_id
            ).first()
            if not parent:
                break
            root = parent
        if root.relation_type == "MASTER_PERSONA":
            master_owner = db.query(User).filter(User.id == root.user_id).first()
    
    # Atanın bilgilerini dict'e çevir (chat fonksiyonu için)
    ancestor_data = {
        "id": ancestor.id,
        "full_name": ancestor.full_name,
        "relation_type": ancestor.relation_type,
        "birth_year": ancestor.birth_year,
        "death_year": ancestor.death_year,
        "temperament": ancestor.temperament,
        "backstory": ancestor.backstory,
        "photo_url": ancestor.photo_url,
    }
    
    # Master persona ise: jenerik otomatik değerleri gerçek bilgilerle değiştir.
    # 📚 Eski kayıtlarda isim "Benim Mirasım", hikaye "EVA tarafından otomatik
    #    oluşturuldu" olarak kalmış olabilir — persona bu metinleri kendi
    #    kimliği sanıp "adım Benim Mirasım" diyordu. Burada düzeltiyoruz.
    if master_owner:
        if ancestor_data["full_name"] in ("Benim Mirasım", "Benim Miras", ""):
            ancestor_data["full_name"] = master_owner.username
        if ancestor_data["backstory"] == "EVA tarafından otomatik oluşturuldu":
            ancestor_data["backstory"] = None
        ancestor_data["relation_type"] = (
            "Miras Bırakan" if ancestor.is_legacy_import else "Ben (kendi dijital mirasım)"
        )
    
    # Eksik bilgileri tespit et
    # 📚 Master persona'da "anı/mizaç/hikaye eksik" uyarısı YAPILMAZ:
    #    bu bilgiler zaten EVA'nın ana hafızasından geliyor. Uyarı yapılırsa
    #    persona varise "bilgilerim eksik, fotoğraf yükle" diye yalvarıyordu.
    missing_info = _get_ancestor_missing_info(ancestor) if not master_owner else []
    
    # Varis mi yoksa oluşturan mı? (Miras anahtarıyla eklenen profiller işaretlidir)
    is_heir = bool(ancestor.is_legacy_import)
    
    # Master persona'da fotoğraf/ses eksikse: varise NAZİKÇE ve opsiyonel
    # olarak yüklemesi rica edilir (bilgi eksiği değil, medya zenginleştirmesi).
    optional_media = []
    if master_owner and is_heir:
        if not ancestor.photo_url:
            optional_media.append("fotoğraf")
        if not ancestor.audio_url:
            optional_media.append("ses kaydı")
    
    # 1. Kullanıcı mesajını HEMEN kaydet
    db.add(Message(conversation_id=conv.id, role="user", content=request.message))
    conv.updated_at = datetime.utcnow()
    db.commit()

    try:
        # Gemini'ye gönder — ata persona'sıyla cevap al
        response_text = chat_as_ancestor(
            ancestor_data=ancestor_data,
            user_message=request.message,
            conversation_history=history,
            is_heir=is_heir,
            missing_info=missing_info if is_heir else None,
            eva_owner_user_id=str(master_owner.id) if master_owner else None,
            optional_media=optional_media
        )
        # 2. İptal Kontrolü
        if request.tracking_id and request.tracking_id in CANCELLED_REQUESTS:
            CANCELLED_REQUESTS.remove(request.tracking_id)
            print(f"İSTEK İPTAL EDİLDİ (tracking_id: {request.tracking_id}). Ata'nın yanıtı kaydedilmedi.")
            return LegacyChatResponse(
                response="",
                ancestor_id=ancestor.id,
                ancestor_name=ancestor_data["full_name"],
                conversation_id=conv.id,
            )

        # 3. Asistan (Ata) mesajını kaydet
        db.add(Message(conversation_id=conv.id, role="assistant", content=response_text))
        conv.updated_at = datetime.utcnow()
        db.commit()

        try:
            get_legacy_memory().save_chat_turn(
                ancestor_id=ancestor.id,
                user_message=request.message,
                ancestor_response=response_text,
                ancestor_name=ancestor_data["full_name"],
            )
        except Exception as chroma_err:
            print(f"[ATA] Karakter sohbeti Chroma kaydi basarisiz (devam): {chroma_err}")
        
        return LegacyChatResponse(
            response=response_text,
            ancestor_id=ancestor.id,
            ancestor_name=ancestor_data["full_name"],
            conversation_id=conv.id,
        )
        
    except HTTPException:
        raise
    except ValueError as ve:
        # Tüm LLM sağlayıcıları tükendi (kota bitti, fallback zinciri boş)
        print(f"[ATA] LLM kota hatasi: {ve}")
        ancestor_name = ancestor_data.get("full_name", "Ben")
        fallback_msg = (
            "Bir sorun oluştu, lütfen tekrar dene."
        )
        return LegacyChatResponse(
            response=fallback_msg,
            ancestor_id=ancestor.id,
            ancestor_name=ancestor_name,
            conversation_id=conv.id,
        )
    except Exception as e:
        print(f"[ATA] Sohbet hatasi: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ata sohbetinde bir hata oluştu: {str(e)}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# DEAD MAN'S SWITCH
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/deadman", response_model=DeadManSwitchResponse, status_code=201)
def create_dead_man_switch(
    request: DeadManSwitchCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Dead Man's Switch (Ölüm Anahtarı) oluştur.
    
    📚 Kullanıcı belirli bir süre sisteme giriş yapmazsa,
        belirlediği e-posta adresine miras anahtarı gönderilir.
    """
    # Ata bu kullanıcıya mı ait?
    ancestor = db.query(Ancestor).filter(
        Ancestor.id == request.ancestor_id,
        Ancestor.user_id == current_user.id
    ).first()
    
    if not ancestor:
        raise HTTPException(status_code=404, detail="Ata profili bulunamadı.")
    
    # Anahtar geçerli mi?
    legacy_key = db.query(LegacyKey).filter(
        LegacyKey.id == request.legacy_key_id,
        LegacyKey.ancestor_id == request.ancestor_id,
        LegacyKey.is_active == True
    ).first()
    
    if not legacy_key:
        raise HTTPException(status_code=404, detail="Geçerli bir miras anahtarı bulunamadı.")
    
    # Aynı ata+anahtar için zaten switch var mı?
    existing = db.query(DeadManSwitch).filter(
        DeadManSwitch.user_id == current_user.id,
        DeadManSwitch.ancestor_id == request.ancestor_id,
        DeadManSwitch.legacy_key_id == request.legacy_key_id,
        DeadManSwitch.triggered == False
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Bu ata ve anahtar için zaten aktif bir Dead Man's Switch var."
        )
    
    # Yeni switch oluştur
    new_switch = DeadManSwitch(
        user_id=current_user.id,
        ancestor_id=request.ancestor_id,
        legacy_key_id=request.legacy_key_id,
        notify_email=request.notify_email,
        inactive_days=request.inactive_days,
        last_checkin=datetime.utcnow()
    )
    
    db.add(new_switch)
    db.commit()
    db.refresh(new_switch)
    
    print(f"[SWITCH] Dead Man's Switch olusturuldu: {ancestor.full_name} -> {request.notify_email} "
          f"({request.inactive_days} gun)")
    
    return DeadManSwitchResponse(
        id=new_switch.id,
        ancestor_name=ancestor.full_name,
        notify_email=new_switch.notify_email,
        inactive_days=new_switch.inactive_days,
        last_checkin=new_switch.last_checkin,
        triggered=new_switch.triggered,
        created_at=new_switch.created_at
    )


@router.get("/deadman", response_model=list[DeadManSwitchResponse])
def list_dead_man_switches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kullanıcının tüm Dead Man's Switch'lerini listele.
    """
    switches = db.query(DeadManSwitch).filter(
        DeadManSwitch.user_id == current_user.id
    ).all()
    
    result = []
    for sw in switches:
        ancestor = db.query(Ancestor).filter(Ancestor.id == sw.ancestor_id).first()
        result.append(DeadManSwitchResponse(
            id=sw.id,
            ancestor_name=ancestor.full_name if ancestor else "Bilinmiyor",
            notify_email=sw.notify_email,
            inactive_days=sw.inactive_days,
            last_checkin=sw.last_checkin,
            triggered=sw.triggered,
            created_at=sw.created_at
        ))
    
    return result


@router.post("/deadman/checkin")
def dead_man_checkin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Dead Man's Switch check-in: "Ben hâlâ buradayım!"
    
    📚 Kullanıcı her giriş yaptığında veya bu endpoint'i
        çağırdığında tüm switch'lerinin last_checkin'i güncellenir.
        Bu sayede zamanlayıcı sıfırlanır.
    """
    # Kullanıcının tüm aktif switch'lerini güncelle
    switches = db.query(DeadManSwitch).filter(
        DeadManSwitch.user_id == current_user.id,
        DeadManSwitch.triggered == False
    ).all()
    
    count = 0
    for sw in switches:
        sw.last_checkin = datetime.utcnow()
        count += 1
    
    db.commit()
    
    print(f"[SWITCH] Check-in: {current_user.username} -- {count} switch guncellendi")
    
    return {
        "message": f"{count} Dead Man's Switch güncellendi. Zamanlayıcılar sıfırlandı.",
        "updated_count": count
    }
