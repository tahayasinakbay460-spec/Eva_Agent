"""
config.py - Merkezi Konfigürasyon
===================================
Tüm ayarlar .env dosyasından okunur.
Böylece kod içine asla API anahtarı yazmamış oluruz.
"""
import os
from dotenv import load_dotenv

# .env dosyasını yükle   // otomatik yuklenir
load_dotenv()

class Config:
    """Ana konfigürasyon sınıfı"""

    # --- Uygulama ---
    SECRET_KEY = os.getenv("SECRET_KEY", "eva-dev-secret-key")
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    APP_PORT = int(os.getenv("APP_PORT", 8000))

    # --- LLM ---
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # sadece "gemini"
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # --- ChromaDB ---
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")

    # --- Veritabanı ---
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///eva_users.db")
