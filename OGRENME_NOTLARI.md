# Öğrenme Notları

EVA'yı yeniden yazarken öğrendiğim konular. Kod okurken ya da takıldığımda buraya dönüyorum.

## Anlaşma

- **Ben yazıyorum**, Claude hocalık yapıyor: anlatıyor, ipucu veriyor, kodumu inceliyor.
- **Ben istediğimde** Claude devralıp kodu profesyonel şekilde dolduruyor.
- Frontend'i istediğimde Claude yazıyor, benim odağım backend.

---

## 1. Uvicorn ve FastAPI

- `app = FastAPI()` sadece bir **nesne**. Port açmaz, istek dinlemez.
- **Uvicorn bir sunucu.** Portu açar, gelen isteği `app`'e verir, cevabı geri yollar.
- Benzetme: `app` = mutfak, `uvicorn` = garson.

İki başlatma yolu:

| Komut | Uvicorn'u kim başlatıyor |
|---|---|
| `python main.py` | Benim dosyam, if bloğunun içindeki `uvicorn.run(...)` |
| `uvicorn app.main:app` | Uvicorn'un kendi kodu. Dosyamı import edip `app` değişkenini alıyor |

- `app.main:app` → `app/main.py` dosyasındaki `app` değişkeni (nokta = klasör, iki nokta = değişken)
- `--reload` → dosya kaydedilince sunucu kendini yeniden başlatır
- Komut **bulunduğum klasöre göre** dosyayı arar, o yüzden `backend/` içinden çalıştırıyorum
- `uvicorn ...` ile `python -m uvicorn ...` aynı şey

## 2. `__name__` ve `"__main__"`

- `__name__` Python'un her dosyaya otomatik koyduğu bir **değişken**. İçinde "bu dosyanın adı ne" yazar.
- Dosya **import edilirse** → `__name__` = modülün adı (`"app.main"`)
- Dosya **doğrudan çalıştırılırsa** → `__name__` = `"__main__"` (dosyanın adı ne olursa olsun)
- `"main"` ≠ `"__main__"`. Alt çizgiler yazının parçası. Dosyamın adının `main.py` olması tesadüf.
- `if __name__ == "__main__":` sıradan bir if. Anlamı: "programı başlatan dosya bensem..."
- `"__main__"` ile `main()` fonksiyonunun **hiçbir ilgisi yok**. `def main()` sadece bir alışkanlık.
- **Import edince dosya baştan sona çalışır.** if satırı da çalışır ama koşul False olduğu için içine girilmez.
- if olmasaydı uvicorn import ettiği anda ikinci bir sunucu başlardı.
- Kod okurken: if'in **içi** = doğrudan çalıştırılınca olacaklar, **dışı** = her durumda çalışanlar.
- Başında ve sonunda `__` olan isimlere **dunder** denir, Python'un özel şeyleridir.

Deney: dosyanın en üstüne `print(repr(__name__))` koyup iki yoldan çalıştır.

## 3. Modül ve class farkı

- `from fastapi import middleware` → bir **modül** (klasör/dosya) gelir
- `from fastapi.middleware.cors import CORSMiddleware` → bir **class** gelir
- Class'lar çağrılabilir, modüller çağrılamaz → hata: `'module' object is not callable`

## 4. Import yolları

- Sunucuyu `backend/` klasöründen başlattığım için Python import'ları `backend/` içinde arıyor.
- O yüzden **bütün proje içi import'lar `app.` ile başlar**: `from app.routers import chat`
- Router app'i import etmez. **`main.py` router'ı import eder**, `app.include_router(...)` ile bağlar.
  Ters yönde yaparsam döngüsel import (circular import) hatası alırım.
- **Python ilk hatada durur.** Bir hatayı düzeltince bir sonraki görünür, normal.

## 5. venv

- Bilgisayarda iki Python var: sistemdeki ve projenin `venv`'i.
- Uvicorn venv'deki Python'la çalışıyor. Paketi venv aktif değilken kurarsam venv onu göremez.
- Aktif etmek: `.\venv\Scripts\Activate.ps1` → satır başında `(venv)` görünmeli
- PowerShell script hatası verirse bir kere: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- VS Code'da sağ alttan interpreter olarak `venv\Scripts\python.exe` seçilmeli

## 6. Pydantic ve isteklerin parametreye gelmesi

- FastAPI parametreyi **sırasına ya da adına göre değil, tipine göre** doldurur:

| Parametre tipi | Veri nereden gelir |
|---|---|
| `BaseModel`'den türeyen class | Request body (JSON) |
| `str`, `int` gibi basit tipler | URL (`?x=5`) |
| `Depends(fonksiyon)` | O fonksiyonun sonucu |

- Akış: JSON gelir → şemayla kontrol edilir → nesne oluşturulur → fonksiyonuma verilir
- Alanlara `.` ile ulaşırım: `chat_message.message`
- Veri yanlış/eksikse FastAPI fonksiyonumu **hiç çağırmadan** 422 döner
- Pydantic olmasa: `Request` alıp `await request.json()` ile elle okurum, bütün kontrolleri ben yazarım, `/docs` da body'yi bilemez
- Şema bir **sözleşme**: "şu veri gelecek, şu cevap gidecek"
- `response_model=...` ve `-> Şema` aynı işi yapar, biri yeterli. Cevap şemaya uymazsa 500 olur.

## 7. GET ve POST

- **GET** = "bana göster", body taşımaz. Tarayıcı adres çubuğu **her zaman** GET atar.
- **POST** = "sana gönderiyorum", body taşır. Mesaj göndermek POST'tur.
- POST'u test etmek için: `http://127.0.0.1:8000/docs` → Try it out → Execute

## 8. HTTP durum kodları

| Kod | Anlamı | Fonksiyonum çalıştı mı |
|---|---|---|
| 200 | Tamam, işte cevap (benim `return`'ümden) | ✅ |
| 404 | Böyle bir adres yok | ❌ |
| 405 | Adres var ama bu yöntemi (GET/POST) kabul etmiyor | ❌ |
| 422 | Doğru yere geldin ama veri eksik/yanlış (Pydantic) | ❌ |
| 500 | Fonksiyonum çalıştı ama içeride bir şey patladı | ✅ (yarıda) |

Hata mesajını okumak: `loc` = sorunun yeri (`["body", "message"]` gibi), `msg` = ne olduğu, `input` = gerçekte ne geldi/gitti.

## 9. Uvicorn logları

Otomatik gelir, ben yazmam (`log_level="info"`):
- `Started server process [PID]` → sunucu başladı
- `Application startup complete` → hazır
- `Uvicorn running on http://127.0.0.1:8000` → bu adreste dinliyor
- `"GET / HTTP/1.1" 200 OK` → biri istek attı, şu kodla cevap verildi
- Tarayıcı `/favicon.ico`'yu otomatik ister, 404 alması normal

## 10. LLM API seçimi

- "Live" / "Realtime" API'ler (Gemini Live, OpenAI Realtime) **sesli konuşma** için. Yazılı sohbet için gereksiz ve pahalı.
- Yazılı sohbette hız = **ilk kelimenin gelme süresi** + **streaming** (cevabı kelime kelime basmak).
- Şimdilik: **Groq ücretsiz katman + streaming.**

## 11. Ayarlar ve `.env`

- Gizli bilgiler (API anahtarı, DB adresi) koda yazılmaz, `backend/.env` içinde `ANAHTAR=değer` olarak durur.
- Dosyanın adı tam olarak **`.env`** (başında nokta). `env` olursa `.gitignore` onu korumaz.
- **`os.getenv` `.env` dosyasını okumaz**, sadece ortam değişkenlerine bakar. Önce `load_dotenv()` (python-dotenv) çağrılmalı.
- `os.getenv` değer yoksa sessizce `None` döner. Alternatif: pydantic-settings `BaseSettings` (eksik ayarda açılışta hata verir, tipleri çevirir).

## 12. LLM'e bağlanmak (Groq)

- Mimari: **router** ince (isteği al, servise ver, cevabı döndür), **service** asıl işi yapar (`services/agent.py`).
  Sağlayıcı değişirse sadece service değişir.
- "Motor çalıştırmak" yok. Model Groq'un sunucusunda zaten çalışıyor, ben internetten istek atıyorum.
- Her LLM kütüphanesi 3 adım: **istemciyi oluştur** (bir kere, fonksiyonun dışında) → **mesajları gönder** → **cevabın metnini çıkar**.
- Mesaj listesi: `system` (kişilik/talimat), `user` (kullanıcı), `assistant` (modelin önceki cevapları).
- Cevabın yazısı derinde: `response.choices[0].message.content` (`choices` bir liste, `message` bir nesne, `content` yazı).
- Syntax'ı ezberlemek gerekmiyor, mantığı bilmek yeterli. Gerekince dokümana bakılır.

## 13. Sözleşme: "Bu sözlük kime gidiyor?"

- Kendi API'min cevabındaki anahtarları **ben** seçerim (`ReplyMessage` şemasına uyduğu sürece).
- Groq'a giden `messages` içindeki anahtarları **Groq** belirler: tam olarak `role` ve `content`. Yanlış yazarsam **400 Bad Request**.
- Groq'un 400'ü, benim API'mdeki 422'nin karşılığı: "isteğin sözleşmeye uymuyor".
- Nokta ile erişim (`nesne.content`) ≠ sözlük anahtarı (`{"content": ...}`).
- Hata mesajındaki `messages.0` = `messages` listesinin 0. elemanı.

## 14. VS Code

- **Auto Save**: File → Auto Save. Sekmede `●` varsa dosya kaydedilmemiş. `--reload` sadece kayıtlı dosyayı görür.
- **IntelliSense** (isim listesi) açık kalsın. **AI tamamlama** (gri renkte satır öneren) öğrenirken kapalı olsun.
- Kural: Tab'la gelen satırı açıklayamıyorsam silip kendim yazarım.

---

## Açık işler

- [x] `.env` + `app/core/config.py`
- [x] `/chat` Groq'tan gerçek cevap veriyor (2026-10-15, ilk konuşma ~1 sn)
- [ ] `main.py`: test `print`'ini ve kullanılmayan `get_db` import'unu sil
- [ ] `routers/chat.py`: kullanılmayan `WebSocket`, `WebSocketDisconnect`, iki kere yazılmış import
- [ ] `services/agent.py`: `global client` satırı, kullanılmayan `MEMORY_INJECTION_TEMPLATE`
- [ ] `core/system_propmt.py` → `system_prompt.py`, içindeki "LangChain" notu
- [ ] `models/chat.py`: class adı `chat` → `Chat`, kullanılmayan `engine`
- [ ] `database.py`: `declarative_base`'i `sqlalchemy.orm`'dan al
- [ ] `.env`: `API_KEY` → `GROQ_API_KEY`
- [ ] `requirement.txt` → UTF-8 `requirements.txt` (sonunda **s**, groq ve python-dotenv dahil)
