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

    # --- LLM Sağlayıcılar ---
    # Google Gemini
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # NVIDIA NIM
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")

    # DeepSeek
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # Groq
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # OpenRouter
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

    # SambaNova
    SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")
    SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.1-8B-Instruct")

    # --- LLM Genel ---
    # Ana sağlayıcı (fallback sırası buna göre belirlenir)
    # nvidia | gemini | deepseek | groq | openrouter | sambanova
    LLM_PROVIDER = (
        os.getenv("LLM_PROVIDER")
        or ("nvidia" if os.getenv("NVIDIA_API_KEY") else "gemini")
    ).strip().lower()

    # Virgülle ayrılmış fallback sırası. Boşsa otomatik sıra kullanılır.
    # Örnek: "gemini,deepseek,nvidia,groq"
    LLM_FALLBACK_ORDER = os.getenv("LLM_FALLBACK_ORDER", "")

    # --- ChromaDB ---
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")

    # --- Veritabanı ---
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///eva_users.db")
