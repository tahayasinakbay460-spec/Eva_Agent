# EVA — Geçmiş

Ne yaptık, nerede kaldık, nasıl çalıştırılır. Her oturum sonunda güncellenir.

---

## 16 Ekim 2026 — Faz 0 iskeleti

### Ne yapıldı

- **Eski kod arşivlendi.** Öğrenme döneminde yazdığın kod silinmedi, `archive/learning-phase/` altına taşındı. Hiçbir yerden kullanılmıyor, istediğinde bakabilirsin.
- **Klasör adları senin alıştığın düzende.** CLAUDE.md `services/`, `libs/` gibi adlar öneriyordu. Bunun yerine `backend/` ve `frontend/` kullandık. Bu karar `docs/adr/0001-folder-layout.md` dosyasında yazılı.
- **Backend sıfırdan yazıldı.** FastAPI, veritabanı, giriş sistemi, sohbet ve EVA'nın kişiliği.
- **Frontend sıfırdan yazıldı.** Next.js ile, verdiğin telefon tasarımına benzeyen ana sayfa ve çalışan sohbet ekranı.
- **25 test yazıldı.** Hepsi geçiyor. Lint ve tip kontrolü de temiz.

### Çalışan şeyler

- İsmini yazıp giriş yapmak (sadece geliştirme için, gerçek giriş değil).
- Ana sayfa tasarımı.
- EVA ile sohbet: cevap kelime kelime akarak geliyor, sohbet geçmişi kaydediliyor.
- Başka kullanıcının sohbetini görememe koruması.

### Henüz çalışmayan şeyler

- **EVA gerçekten konuşmuyor.** Şu an sahte (mock) sağlayıcı yazdığını geri söylüyor. API anahtarı gerekiyor.
- **Ana sayfadaki bazı kartlar sahte.** "Ruh halin: İyi" ve "1.2 saat" uydurma değerler. Temizlenecek.
- **"Yakında" yazan her yer:** sesli görüşme, görüntülü görüşme, anılar, Miras, Karakter Stüdyosu, analiz, keşfet, profil.
- **Gerçek giriş yok.** Passkey ve MFA için karar bekleniyor.
- **Docker yok.** Postgres yerine geçici olarak SQLite kullanılıyor.
- **CI yok.** GitHub'da otomatik test kurulmadı.

---

## Nasıl çalıştırılır

Önce eski terminalde açık kalan uvicorn varsa Ctrl+C ile kapat (8000 portunu tutuyor).

**Terminal 1 — backend:**
```powershell
cd C:\Users\HYPER\Desktop\EVA\backend
uv run uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend:**
```powershell
cd C:\Users\HYPER\Desktop\EVA\frontend
npm run dev
```

Tarayıcıda `http://localhost:3000` aç. API'yi denemek için `http://localhost:8000/docs`.

**Testler:**
```powershell
cd backend
uv run pytest
```

**Gerçek EVA cevabı için:** `backend\.env` dosyasına `ANTHROPIC_API_KEY=...` ekle ve `EVA_LLM_PROVIDER_OVERRIDE=mock` satırını sil.

---

## Kodu nasıl okursun

Hepsini okumana gerek yok. Bir mesajın yolculuğunu takip et, gerisi zamanla gelir.

**Bir sohbet mesajının yolu:**

1. `frontend/src/app/chat/page.tsx` — Sen mesajı yazıp Enter'a basıyorsun.
2. `frontend/src/lib/api/client.ts` — `sendMessage` fonksiyonu mesajı backend'e yolluyor.
3. `backend/app/routers/chat.py` — İstek buraya geliyor. Senin eski `routers/chat.py` dosyanın aynı görevi.
4. `backend/app/services/chat_service.py` — `stream_reply` fonksiyonu asıl işi yapıyor: geçmişi okuyor, mesajı kaydediyor, modele soruyor, cevabı kaydediyor. Senin eski `services/agent.py` dosyanın büyümüş hali.
5. `backend/app/persona/compiler.py` — EVA'nın sistem prompt'unu parça parça kuruyor. Senin eski `system_propmt.py` dosyanın yerini aldı.
6. `backend/app/providers/anthropic.py` — Modele giden çağrı. Eski kodundaki `client.chat.completions.create` satırının karşılığı.

**Klasörler ne işe yarıyor (backend/app):**

| Klasör | Görevi | Eski kodundaki karşılığı |
|---|---|---|
| `core/` | Ayarlar, güvenlik, rate limit | `core/config.py` |
| `models/` | Veritabanı tabloları | `models/history.py` |
| `schemas/` | İstek ve cevap şekilleri (Pydantic) | `schemas/chat.py` |
| `routers/` | URL'ler ve uç noktalar | `routers/chat.py` |
| `services/` | İş mantığı | `services/agent.py` |
| `persona/` | EVA'nın kişiliği ve kuralları | `core/system_propmt.py` |
| `providers/` | Model sağlayıcıları (Claude, mock) | yoktu, Groq doğrudan çağrılıyordu |

---

## Yeni kavramlar sözlüğü

Kodda karşına çıkacak, muhtemelen yeni olan kavramlar. Takıldıkça buraya bak.

- **async / await:** Bir iş beklerken (veritabanı, ağ) sunucunun başka isteklere bakabilmesi. `async def` fonksiyonları `await` ile çağrılır.
- **SSE (Server-Sent Events):** Sunucunun cevabı tek seferde değil, parça parça göndermesi. EVA'nın cevabının kelime kelime gelmesi bu sayede.
- **Streaming (akış):** Modelin cevabı bitirmesini beklemeden, ürettikçe göndermesi.
- **Alembic / migration:** Veritabanı tablolarındaki değişikliklerin sürüm kaydı. Tablo değişince yeni bir migration dosyası oluşur.
- **Dependency (Depends):** FastAPI'nin bir fonksiyona otomatik değer vermesi. Örneğin `CurrentUser` ile giriş yapmış kullanıcı otomatik geliyor.
- **Token:** Giriş yapınca verilen anahtar. Her istekte gönderilir. Veritabanında sadece özeti (hash) tutulur.
- **Rate limit:** Bir kullanıcının dakikada kaç istek atabileceğinin sınırı. Saldırıya ve maliyete karşı koruma.
- **IDOR:** Başkasının verisine ID'sini tahmin ederek erişme açığı. Her sorguda `user_id` kontrolü bunu engelliyor.
- **Idempotency key:** Aynı mesaj iki kez gönderilirse (internet koptu, tekrar denedin) iki kez kaydedilmemesi için kullanılan benzersiz anahtar.
- **Provider / adaptör:** Model şirketine (Anthropic, Groq) bağlanan katman. Şirket değişirse sadece bu katman değişir.
- **Mock:** Gerçek servisin taklidi. Ücretsiz ve internetsiz test için.
- **Protocol:** Python'da "bu sınıfın şu fonksiyonları olmalı" diyen sözleşme. `providers/base.py` içinde.
- **Prompt cache:** Sistem prompt'unun değişmeyen kısmını modelin hatırlaması. Hem hızlı hem ucuz.
- **OpenAPI:** Backend'in kendi uç noktalarını tarif eden dosya. Frontend tiplerini bundan otomatik üretiyoruz.
- **uv:** pip ve venv'in yerine geçen hızlı Python paket yöneticisi. `uv run` doğru ortamı kendisi bulur.
- **ADR:** Mimari karar kaydı. "Neden böyle yaptık" sorusunun cevabı `docs/adr/` içinde.

---

## Açık sorular (sonraki oturum)

1. EVA için hangi API anahtarı? Anthropic mi, Groq adaptörü mü yazılsın?
2. Docker Desktop kurulacak mı, yoksa bir süre SQLite ile mi devam?
3. Platform önceliği: önce web mi, mobil (Expo) da başlasın mı?
4. Gerçek giriş (passkey + MFA) için hangi çözüm?

## Sıradaki adım önerisi

1. EVA'yı gerçek modele bağlamak (API anahtarı).
2. Ana sayfadaki sahte kartları temizlemek.
3. Faz 1: hafıza ve anılar, "EVA ne biliyor" ekranı.

Bundan sonra daha küçük adımlarla ilerleyip her adımda yeni kavramları açıklayacağız.
