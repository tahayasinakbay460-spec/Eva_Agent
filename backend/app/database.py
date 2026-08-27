"""
database.py - Veritabanı Bağlantısı
======================================
SQLAlchemy ile MySQL bağlantısı (Faz 3).
Sürücü: PyMySQL — bağlantı dizesi .env'den okunur.
"""
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import Config

# Veritabanı motoru
engine = create_engine(Config.DATABASE_URL)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tüm modellerin miras alacağı temel sınıf
Base = declarative_base()


def get_db():
    """
    FastAPI dependency injection için DB session sağlar.
    Her istek için yeni bir session açar, bittikten sonra kapatır.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Uygulama başlarken tabloları oluşturur."""
    from app.models import user   # User tablosu
    from app.models import chat   # Conversation + Message tabloları
    from app.models import legacy # Faz 8: Ancestor + AncestorMemory + LegacyKey + DeadManSwitch
    Base.metadata.create_all(bind=engine)
    _run_mini_migrations()
    print("Veritabani tablolari hazir.")


def _run_mini_migrations():
    """
    Basit kolon ekleme migration'ları.
    
    📚 Neden gerekli?
        create_all() sadece OLMAYAN tabloları oluşturur — var olan tabloya
        yeni kolon EKLEMEZ. Modele yeni kolon eklediğimizde (ör: expires_at),
        eski veritabanlarında bu kolon eksik kalır ve sorgular patlar.
        Alembic gibi tam bir migration aracı kurmak yerine, küçük projede
        bu hafif kontrol yeterlidir.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    def _add_column_if_missing(table: str, column: str, ddl: str):
        """Tabloda kolon yoksa ALTER TABLE ile ekler."""
        if table not in tables:
            return
        columns = [col["name"] for col in inspector.get_columns(table)]
        if column not in columns:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
            print(f"Migration: {table}.{column} kolonu eklendi.")
    
    # legacy_keys.expires_at — miras anahtarı geçerlilik süresi (Faz 8 güvenlik)
    _add_column_if_missing("legacy_keys", "expires_at", "expires_at DATETIME")
    
    # İzin modeli: anahtar/karakter nesiller arası aktarılabilir mi?
    _add_column_if_missing("legacy_keys", "is_transferable",
                           "is_transferable BOOLEAN DEFAULT 0")
    _add_column_if_missing("ancestors", "is_transferable",
                           "is_transferable BOOLEAN DEFAULT 0")

    # Karakter sohbetleri Eva geçmişinden ayrı tutulur
    _add_column_if_missing("conversations", "ancestor_id", "ancestor_id INTEGER")
