"""
database.py - Veritabanı Bağlantısı
======================================
SQLAlchemy ile SQLite bağlantısı.
Flask-SQLAlchemy olmadan, saf SQLAlchemy kullanıyoruz.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import Config

# Veritabanı motoru
engine = create_engine(
    Config.DATABASE_URL,
    connect_args={"check_same_thread": False}  # Yani Sql lite birden fazla aynı anda baglantı kurmasına ızın veriyor. 
)

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
    from app.models import user  # modeli import et ki Base.metadata görsün
    Base.metadata.create_all(bind=engine)
    print("Veritabani tablolari hazir.")
