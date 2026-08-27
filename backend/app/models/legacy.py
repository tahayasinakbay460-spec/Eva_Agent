"""
models/legacy.py — Ata Teknolojisi Veritabanı Modelleri (Faz 8)
================================================================
Dijital Miras sistemi için 4 tablo:

1. Ancestor       → Ata/kişi profili (isim, mizaç, hikaye, fotoğraf vb.)
2. AncestorMemory → O kişiye ait yüklenen anılar (metin/PDF)
3. LegacyKey      → Miras anahtarları (varise verilecek benzersiz anahtar)
4. DeadManSwitch  → Ölüm anahtarı (uzun süre giriş yoksa otomatik bildirim)

📚 Öğretici Not:
    Bu tablolar mevcut User tablosuna ForeignKey ile bağlıdır.
    Bir kullanıcı birden fazla ata oluşturabilir.
    Her atanın birden fazla anısı ve birden fazla anahtarı olabilir.
"""

from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Ancestor(Base):
    """
    Ata/Kişi profil tablosu.
    
    📚 Her kayıt bir dijital persona'yı temsil eder.
        Kullanıcı dedesini, babasını, kız arkadaşını veya
        bizzat kendisini bu tabloya kaydedebilir.
        
    Alanlar:
        full_name    → Atanın tam adı (ör: "Mehmet Dede")
        birth_year   → Doğum yılı (isteğe bağlı, ör: "1940")
        death_year   → Vefat yılı (isteğe bağlı, ör: "2015")
        relationship → Kullanıcıyla ilişkisi (ör: "Dede", "Baba", "Kız Arkadaş", "Ben")
        temperament  → Mizaç özellikleri (ör: "Sakin, bilge, ağırbaşlı, espritüel")
        backstory    → Kısa hayat hikayesi (ör: "Köyde büyüdü, İstanbul'a göç etti...")
        photo_url    → Fotoğraf yolu (isteğe bağlı, frontend'den yüklenir)
    """
    __tablename__ = "ancestors"

    # Benzersiz kimlik — otomatik artar
    id = Column(Integer, primary_key=True, index=True)
    
    # Bu atayı hangi kullanıcı oluşturdu?
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),  # Kullanıcı silinirse ataları da silinir
        nullable=False,
        index=True
    )

    # ── Temel Bilgiler ──
    full_name    = Column(String(200), nullable=False)           # Atanın adı
    birth_year   = Column(String(10), nullable=True)             # Doğum yılı (opsiyonel)
    death_year   = Column(String(10), nullable=True)             # Vefat yılı (opsiyonel)
    relation_type = Column(String(100), nullable=False)           # Akrabalık: "Dede", "Baba", "Ben"
    
    # ── Kişilik Bilgileri ──
    temperament  = Column(Text, nullable=True)                   # Mizaç: "sakin, bilge, espritüel"
    backstory    = Column(Text, nullable=True)                   # Hayat hikayesi
    
    # ── Medya ──
    photo_url    = Column(String(500), nullable=True)            # Fotoğraf dosya yolu
    audio_url    = Column(String(500), nullable=True)            # Ses dosya yolu
    video_url    = Column(String(500), nullable=True)            # Video dosya yolu
    pdf_url      = Column(String(500), nullable=True)            # PDF dosya yolu
    
    # ── Miras (Import) Bilgileri ──
    is_legacy_import = Column(Boolean, default=False)            # Başkasının miras anahtarıyla mı eklendi?
    original_ancestor_id = Column(Integer, nullable=True)        # Klonlandıysa orijinal atanın ID'si
    # 📚 Aktarılabilirlik: Miras alınan karakter başkasına aktarılabilir mi?
    #    Anahtarı üreten kişi karar verir (izin modeli). False = tek kişiye özel,
    #    varis bu karakter için yeni anahtar üretemez.
    is_transferable = Column(Boolean, default=False)
    
    # ── Zaman damgaları ──
    created_at   = Column(DateTime, server_default=func.now())   # Oluşturulma tarihi
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # ── İlişkiler (SQLAlchemy ORM) ──
    # Bu ata silinirse, ona ait anılar ve anahtarlar da otomatik silinir
    memories   = relationship("AncestorMemory", back_populates="ancestor",
                              cascade="all, delete-orphan", order_by="AncestorMemory.created_at")
    legacy_keys = relationship("LegacyKey", back_populates="ancestor",
                               cascade="all, delete-orphan")
    user = relationship("User")  # Sahibi olan kullanıcıya kolay erişim

    def __repr__(self):
        return f"<Ancestor id={self.id} name='{self.full_name}' rel='{self.relation_type}'>"


class AncestorMemory(Base):
    """
    Ataya ait yüklenen anılar tablosu.
    
    📚 Her anı bir metin parçasıdır ve ChromaDB'ye de vektör olarak kaydedilir.
        memory_type ile ne tür bir anı olduğu belirtilir.
        chroma_doc_id ile ChromaDB'deki vektör kaydına referans verilir.
    
    Alanlar:
        ancestor_id   → Hangi ataya ait
        memory_type   → "text" (düz metin), "pdf" (PDF'ten çıkarılmış), "story" (hikaye)
        title         → Anının başlığı (ör: "Dedemin köy hikayeleri")
        content       → Anının tam metni
        chroma_doc_id → ChromaDB'deki vektör kaydının ID'si (RAG için)
    """
    __tablename__ = "ancestor_memories"

    id = Column(Integer, primary_key=True, index=True)
    
    # Hangi ataya ait bu anı?
    ancestor_id = Column(
        Integer,
        ForeignKey("ancestors.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # ── Anı İçeriği ──
    memory_type   = Column(String(20), nullable=False, default="text")  # text / pdf / story
    title         = Column(String(300), nullable=True)                  # Anının başlığı
    content       = Column(Text, nullable=False)                        # Anının tam metni
    chroma_doc_id = Column(String(100), nullable=True)                  # ChromaDB referans ID'si

    created_at = Column(DateTime, server_default=func.now())

    # İlişki: Bu anının sahibi olan ata
    ancestor = relationship("Ancestor", back_populates="memories")

    def __repr__(self):
        return f"<AncestorMemory id={self.id} type='{self.memory_type}' ancestor={self.ancestor_id}>"


class LegacyKey(Base):
    """
    Miras Anahtarı tablosu.
    
    📚 Her anahtar benzersiz bir UUID'dir ve bir atanın dijital mirasına
        erişim sağlar. Kullanıcı bu anahtarı güvendiği birine verir.
        Anahtarla giriş yapan kişi, o atanın persona'sıyla sohbet edebilir.
    
    Alanlar:
        ancestor_id       → Hangi atanın mirası
        created_by_user_id → Anahtarı kim oluşturdu
        key_hash          → Benzersiz UUID anahtar (ör: "EVA-A1B2-C3D4-E5F6-G7H8")
        heir_email        → Varisin e-posta adresi (opsiyonel, Dead Man's Switch için)
        is_active         → Anahtar aktif mi? (iptal edilebilir)
    """
    __tablename__ = "legacy_keys"

    id = Column(Integer, primary_key=True, index=True)
    
    # Hangi atanın anahtarı?
    ancestor_id = Column(
        Integer,
        ForeignKey("ancestors.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Anahtarı kim oluşturdu?
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # ── Anahtar Bilgileri ──
    key_hash   = Column(String(50), unique=True, nullable=False, index=True)  # Benzersiz anahtar
    heir_email = Column(String(200), nullable=True)                           # Varisin e-postası
    is_active  = Column(Boolean, default=True)                                # Aktiflik durumu
    # 📚 İzin modeli: Anahtar sahibi, mirasın nesiller arası aktarılabilir olup
    #    olmayacağına karar verir. True ise varis de kendi anahtarını üretebilir.
    is_transferable = Column(Boolean, default=False)
    
    # ── Güvenlik: Geçerlilik Süresi ──
    # 📚 NULL = süresiz anahtar. Dolu ise bu tarihten sonra anahtar geçersiz olur.
    #    Anahtar üretirken kullanıcı "kaç gün geçerli olsun" seçebilir.
    expires_at = Column(DateTime, nullable=True)
    
    # ── Zaman damgaları ──
    created_at  = Column(DateTime, server_default=func.now())
    last_used_at = Column(DateTime, nullable=True)  # En son ne zaman kullanıldı

    # İlişkiler
    ancestor = relationship("Ancestor", back_populates="legacy_keys")
    creator  = relationship("User")

    def __repr__(self):
        return f"<LegacyKey id={self.id} key='{self.key_hash}' active={self.is_active}>"


class DeadManSwitch(Base):
    """
    Dead Man's Switch (Ölüm Anahtarı) tablosu.
    
    📚 Kullanıcı belirli bir süre sisteme giriş yapmazsa,
        önceden belirlediği e-posta adresine otomatik olarak
        miras anahtarı gönderilir.
    
    Nasıl çalışır:
        1. Kullanıcı switch ayarlar → inactive_days (varsayılan 180 gün)
        2. Her giriş → last_checkin güncellenir
        3. Periyodik kontrol: now() - last_checkin > inactive_days ise → tetikle
        4. Tetiklenince → notify_email'e anahtar gönderilir, triggered=True olur
    
    Alanlar:
        user_id        → Switch'in sahibi
        ancestor_id    → Hangi atanın mirası gönderilecek
        legacy_key_id  → Hangi anahtar gönderilecek
        notify_email   → Bildirim e-posta adresi
        inactive_days  → Kaç gün sonra tetiklensin (varsayılan 180)
        last_checkin   → En son giriş zamanı
        triggered      → Daha önce tetiklendi mi?
    """
    __tablename__ = "dead_man_switches"

    id = Column(Integer, primary_key=True, index=True)
    
    # Switch'in sahibi kim?
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Hangi atanın mirası?
    ancestor_id = Column(
        Integer,
        ForeignKey("ancestors.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Hangi anahtar gönderilecek?
    legacy_key_id = Column(
        Integer,
        ForeignKey("legacy_keys.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # ── Switch Ayarları ──
    notify_email  = Column(String(200), nullable=False)        # Kime gönderilecek
    inactive_days = Column(Integer, default=180)               # Kaç gün sonra tetiklensin
    last_checkin  = Column(DateTime, server_default=func.now())  # Son giriş zamanı
    triggered     = Column(Boolean, default=False)             # Tetiklendi mi?
    
    created_at = Column(DateTime, server_default=func.now())

    # İlişkiler
    user       = relationship("User")
    ancestor   = relationship("Ancestor")
    legacy_key = relationship("LegacyKey")

    def __repr__(self):
        return f"<DeadManSwitch id={self.id} user={self.user_id} days={self.inactive_days} triggered={self.triggered}>"
