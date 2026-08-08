# 🤖 Eva — Yapay Zeka Asistanı

> Dürüst, eleştirel ve uzun süreli hafızaya sahip kişisel yapay zeka dostun.

Eva standart bir chatbot değil. Seni gerçekten tanıyan, gerektiğinde sert ama her zaman dürüst, RAG tabanlı uzun süreli hafızaya sahip bir yapay zeka asistanı.

---

## 🧠 Özellikler

- **Uzun Süreli Hafıza (RAG)** — ChromaDB ile vektör tabanlı hafıza. Eski konuşmalar semantik olarak aranır ve bağlam olarak LLM'e enjekte edilir.
- **Google Gemini entegrasyonu** — `google-genai` SDK'sı üzerinden Gemini 1.5 Flash modeli.
- **Kişilik Sistemi** — System Prompt ile tanımlı, karakterini koruyan, yaltaklanmayan Eva.
- **Markdown Desteği** — Eva'nın cevapları frontend'de `marked.js` ile render edilir.
- **Temiz Mimari** — FastAPI + SQLAlchemy + ChromaDB + Pydantic ile modüler, ölçeklendirilebilir yapı.

---

## 🛠️ Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| **Backend Framework** | Python 3.12, FastAPI, Uvicorn |
| **AI / LLM** | Google Gemini 1.5 Flash (`google-genai` SDK) |
| **Uzun Süreli Hafıza** | ChromaDB (vektör DB), RAG sistemi |
| **Kısa Süreli Hafıza** | Oturum içi konuşma geçmişi (frontend'de tutuluyor) |
| **Veritabanı** | SQLite + SQLAlchemy ORM |
| **Veri Doğrulama** | Pydantic v2 |
| **Frontend** | Vanilla HTML / CSS / JavaScript |
| **Markdown Render** | marked.js |

---

## 📁 Proje Yapısı

```
EVA/
├── frontend/
│   ├── index.html          # UI yapısı (header, chat, input alanı)
│   ├── style.css           # Tasarım sistemi (dark mode, glassmorphism, animasyonlar)
│   └── script.js           # Frontend mantığı (API iletişimi, DOM işlemleri)
│
├── backend/
│   ├── run.py              # Giriş noktası — uvicorn'u başlatır
│   ├── requirements.txt    # Python bağımlılıkları
│   ├── .env                # API anahtarları (gitignore'da — paylaşma!)
│   │
│   └── app/
│       ├── main.py         # FastAPI app, CORS, router kayıtları, static file serve
│       ├── config.py       # .env'den ayar okuma (Config sınıfı)
│       ├── database.py     # SQLAlchemy engine, session factory, Base
│       │
│       ├── core/
│       │   ├── eva_agent.py    # Gemini istemcisi, chat_with_eva() fonksiyonu
│       │   ├── memory.py       # ChromaDB RAG hafıza sistemi (EvaMemory sınıfı)
│       │   └── prompts.py      # Eva'nın kişilik ve system prompt tanımı
│       │
│       ├── models/
│       │   └── user.py         # SQLAlchemy User modeli (tablo tanımı)
│       │
│       ├── routes/
│       │   └── chat.py         # /api/chat ve /api/chat/memory-stats endpoint'leri
│       │
│       └── schemas/
│           └── chat.py         # Pydantic şemaları (ChatRequest, ChatResponse vb.)
│
├── .gitignore
└── README.md
```

---

## 🚀 Kurulum & Çalıştırma

### Ön Gereksinimler
- Python 3.10+
- Google AI Studio API Key → [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

---

### 1. Projeyi Klonla

```bash
git clone https://github.com/KULLANICI_ADIN/EVA.git
cd EVA
```

### 2. Backend Kurulumu

```bash
cd backend

# Sanal ortam oluştur
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# Bağımlılıkları yükle
pip install -r requirements.txt
```

### 3. `.env` Dosyasını Oluştur

`backend/` klasörüne `.env` dosyası aç ve şunu yaz:

```env
GOOGLE_API_KEY=AIzaSy...buraya_kendi_keyin_yaz
GEMINI_MODEL=gemini-1.5-flash
APP_PORT=8000
DEBUG=True
DATABASE_URL=sqlite:///eva_users.db
CHROMA_DB_PATH=./chroma_db
SECRET_KEY=guclu-bir-secret-key-yaz
```

> ⚠️ `.env` dosyası `.gitignore`'da olduğu için GitHub'a yüklenmez. Bu dosyayı asla paylaşma.

### 4. Backend'i Başlat

```bash
# backend/ klasöründeyken:
python run.py
```

Backend `http://localhost:8000` adresinde çalışır.
Swagger UI (otomatik API dökümantasyonu): `http://localhost:8000/docs`

### 5. Frontend'i Aç

Frontend ayrı bir sunucuya ihtiyaç duymaz. Backend zaten statik dosyaları serve eder:

```
http://localhost:8000/
```

Veya `frontend/index.html` dosyasını doğrudan tarayıcıda açabilirsin.

---

## 📡 API Endpoint'leri

| Method | URL | Açıklama |
|--------|-----|----------|
| `GET` | `/api/health` | Backend sağlık kontrolü |
| `POST` | `/api/chat` | Eva ile konuşma (hafıza entegre) |
| `GET` | `/api/chat/memory-stats?user_id=...` | Hafıza kayıt sayısı |

### Örnek İstek

```json
POST /api/chat
Content-Type: application/json

{
  "message": "Eva, nasılsın?",
  "user_id": "kullanici_123",
  "history": [
    { "role": "user", "content": "Merhaba" },
    { "role": "assistant", "content": "Selam! Ne var ne yok?" }
  ]
}
```

### Örnek Yanıt

```json
{
  "response": "İyiyim, teşekkürler. Sen nasılsın?",
  "user_id": "kullanici_123"
}
```

---

## 🗺️ Proje Yol Haritası

- [x] **Faz 1 — MVP**: Temel sohbet, Gemini entegrasyonu, RAG hafıza sistemi (ChromaDB), FastAPI backend, vanilla JS frontend
- [x] **Faz 2 — Auth & Çok Kullanıcı**: JWT tabanlı kayıt/giriş, şifrelenmiş parola, kullanıcıya özel izole hafıza, korumalı endpoint'ler
- [ ] **Faz 3 — Kullanıcı Mesajları**: Kullanıcın eski mesajlarını liste sol panelde gemini gibi gostereme ve veritabanını mysqle cevirme
- [ ] **Faz 4 — Ses**: STT (konuşmayı metne) ve TTS (metni sese) entegrasyonu
- [ ] **Faz 5 — Görsel**: Kamera erişimi ve duygu analizi
- [ ] **Faz 6 — Proaktiflik**: Zamanlanmış bildirimler ve hatırlatıcılar
- [ ] **Faz 7 — Monetizasyon**: Mini oyunlar & reklam entegrasyonu

---

## 🔐 Güvenlik Notları

- API anahtarları `.env` dosyasında tutulur, asla koda yazılmaz
- `.gitignore` ile `.env`, `chroma_db/`, `eva_users.db` ve `venv/` GitHub'a yüklenmez
- Production ortamında `DEBUG=False` yapılmalı ve `SECRET_KEY` güçlü olmalı

---

## 📄 Lisans

MIT License — Dilediğin gibi kullan, fork et, geliştir.
