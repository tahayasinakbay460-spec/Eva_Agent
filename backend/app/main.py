"""
app/main.py - FastAPI Uygulaması
==================================
Flask'taki __init__.py'nin karşılığı.

📚 Flask vs FastAPI karşılaştırması:
    Flask:   app = Flask(__name__)  → blueprint kaydet
    FastAPI: app = FastAPI()        → router include et

Burada yapılanlar:
1. FastAPI uygulaması oluştur
2. CORS ayarla (frontend erişebilsin)
3. Startup/shutdown eventleri tanımla
4. Router'ları bağla
5. Statik dosyaları (HTML/CSS/JS frontend) serve et
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.database import create_tables
from app.routes.chat import router as chat_router
from app.routes.auth import router as auth_router
from app.routes.history import router as history_router
from app.routes.legacy import router as legacy_router  # Faz 8: Ata Teknolojisi


# ─── Lifespan (Startup / Shutdown) ─────────────────────────────────────────
# 📚 Lifespan: Uygulama başlarken ve kapanırken çalışacak kod.
#    Flask'taki @app.before_first_request'in karşılığı.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP — uygulama başlarken
    print("=" * 50)
    print("  Eva AI Backend Baslatiliyor...")
    print("=" * 50)
    create_tables()
    print("Eva hazir! http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print("=" * 50)

    yield  # Uygulama burada çalışır

    # SHUTDOWN — uygulama kapanırken
    print("Eva kapatiliyor...")


# ─── FastAPI Uygulaması ─────────────────────────────────────────────────────
app = FastAPI(
    title="Eva AI",
    description="Eva — Dürüst, empatik yapay zeka dostun 🤖",
    version="2.0.0",
    lifespan=lifespan
)


# ─── CORS Ayarları ──────────────────────────────────────────────────────────
# 📚 CORS: Tarayıcı güvenlik politikası.
#    Frontend (localhost) → Backend (localhost:8000) isteklerine izin ver.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Geliştirme için tümüne izin ver
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── API Route'ları ─────────────────────────────────────────────────────────
# 📚 Not: Duygu algılama artık tarayıcıda (face-api.js) yapılıyor.
#    Eski /ws/emotion WebSocket endpoint'i ve DeepFace kaldırıldı.
app.include_router(chat_router,    prefix="/api")
app.include_router(auth_router,    prefix="/api/auth")     # /api/auth/register, /login, /me
app.include_router(history_router, prefix="/api/history")  # /api/history/conversations
app.include_router(legacy_router,  prefix="/api/legacy")   # Faz 8: Ata Teknolojisi


# ─── Sağlık Kontrolü ────────────────────────────────────────────────────────
@app.get("/api/health")
def health_check():
    """Backend çalışıyor mu kontrol et."""
    return {"status": "ok", "message": "Eva Backend calisiyor!"}


# ─── Yüklenen Dosyalar (Miras Fotoğraf/Ses/Video/PDF) ───────────────────────
# 📚 routes/legacy.py dosyaları backend/uploads klasörüne kaydeder ve
#    "/api/uploads/..." URL'i döndürür. Bu mount olmadan o URL'ler 404 verir!
UPLOADS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
)
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


# ─── Frontend Statik Dosyaları ───────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend")
FRONTEND_DIR = os.path.abspath(FRONTEND_DIR)

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_login():
        """Ana sayfa → login.html (giriş yapılmamışsa)"""
        return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

    @app.get("/chat")
    def serve_chat():
        """Chat sayfası → index.html (giriş yapılmış kullanıcılar için)"""
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
