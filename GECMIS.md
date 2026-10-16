# EVA — Geçmiş

Ne yaptık, nerede kaldık, nasıl çalıştırılır. Her oturum sonunda güncellenir.

---

## 16 Ekim 2026 (3. oturum) — CI yeşil, passkey ile giriş

### Ne yapıldı

- **Kod GitHub'a gönderildi (push) ve CI ilk kez çalıştı.** İlk denemede frontend'in tip kontrolü düştü: Next.js bazı tipleri `.next/` klasöründe kendisi üretiyor, temiz makinede o klasör yok. Düzeltildi; artık **6 işin 6'sı yeşil**.
- **Giriş kararı: A (kendimiz yazıyoruz).** `docs/adr/0002-authentication.md` dosyasına yazıldı. Önce `docs/threat-model.md` içinde "saldırgan ne yapabilir, biz nasıl engelliyoruz" tablosu yazıldı, sonra kod.
- **Passkey ile hesap açma ve giriş (backend + ekran).** Artık isim yazıp girmek yok:
  1. İsmini yaz, "yapay zekâ olduğunu anladım" ve "18 yaşından büyüğüm" kutularını işaretle.
  2. "Passkey ile hesap oluştur"a bas → Windows Hello / parmak izi / PIN penceresi çıkar → onayla.
  3. Bir dahaki sefere "Zaten hesabım var" → "Passkey ile giriş yap". Kullanıcı adı bile sorulmuyor.
- **22 yeni güvenlik testi.** Gerçek bir parmak izi okuyucuyu taklit eden test cihazıyla: sahte siteden giriş, aynı isteği tekrar gönderme, süresi geçmiş istek, parmak izi doğrulanmadan giriş, kopyalanmış cihaz, bozuk imza, başkasının kimliğine bürünme... Hepsi reddediliyor, hepsi aynı hata mesajıyla (saldırgan hangi kontrolün tuttuğunu öğrenemesin diye).
- **Gerçek tarayıcıda uçtan uca denendi** (Chromium'un sanal parmak izi okuyucusuyla): hesap oluşturma, çıkıp tekrar girme, iptal edilince hata mesajı, ardından sohbet. Hepsi çalıştı, konsolda hata yok.
- **Denerken bulunan 2 hata düzeltildi:** sohbet sayfası yüklenmeden gönderilen mesaj sessizce kayboluyordu; Karakter Stüdyosu kartının görünümü bozulmuştu (bir önceki oturumda benim yüzümden).

**Testler:** 41 → 63, hepsi geçiyor.

### Sonra: e-posta + şifre ile giriş (senin kararın)

Kayıt ekranında artık iki seçenek var: **Passkey (önerilen)** ya da **E-posta + şifre**.

- Şifreyle girişte, şifreden sonra **e-postana 6 haneli bir kod** geliyor. Çünkü tek başına şifre tek kilit; CLAUDE.md iki kilit istiyor. İleride bu ikinci adım doğrulama uygulaması ya da SMS ile değiştirilebilir, sistem buna göre kuruldu.
- Hesap, e-postadaki kod girilince açılıyor; böylece kimse başkasının e-postasıyla hesap açamıyor.
- **Şifremi unuttum:** e-postana kod gelir, yeni şifreni belirlersin, tüm cihazlardaki oturumların kapanır.
- Şifreler veritabanında **Argon2id** ile saklanıyor: şifrenin kendisi değil, geri çevrilemeyen bir özeti.
- Kötü niyetli birine "bu e-posta kayıtlı mı" bilgisi verilmiyor: kayıtlı e-postayla tekrar kayıt olunmaya çalışılırsa ekran aynı görünüyor, gerçek sahibine "hesabın zaten var" maili gidiyor.
- Kod tahminine karşı: kod 10 dakika geçerli, en fazla 5 deneme hakkı var, tek kullanımlık.

**E-posta servisi henüz seçilmedi**, o yüzden mailler gerçekten gitmiyor. Bilgisayarında `backend\dev_mailbox\` klasörüne dosya olarak düşüyor. Kod lazım olunca o klasördeki **en yeni dosyayı** aç. Ekranda da bu ipucu yazıyor (sadece geliştirme modunda).

**Testler:** 63 → 86. Tarayıcıda da baştan sona denendi: şifreyle kayıt, yanlış kod, yanlış şifre, kodla giriş, şifre sıfırlama, yeni şifreyle giriş. Passkey akışı da tekrar denendi, bozulmadı.

### Faz 0'ın durumu

Çıkış kriteri ("CI yeşil; mock'larla uçtan uca sohbet çalışıyor") **karşılandı**. Giriş tarafında kalanlar, sırayla:

1. ~~Yedek giriş~~ → kısmen çözüldü: artık e-posta + şifre ve "Şifremi unuttum" var. Kalan: passkey'li hesaba sonradan şifre eklemek (ve tersi), kurtarma kodları.
2. Oturum anahtarının daha güvenli saklanması (kısa ömürlü anahtar + yenileme, httpOnly çerez).
3. Hassas işlemlerde (Miras, ses kaydı vb.) tekrar parmak izi isteme (step-up).
4. "Açık oturumlarım / cihazlarım" ekranı.

### Senin yapman gereken (bir kere)

Veritabanına yeni tablolar eklendi. Backend'i başlatmadan önce:
```powershell
cd C:\Users\HYPER\Desktop\EVA\backend
uv sync
uv run alembic upgrade head
```
Eski `venv` ile değil, `uv run` ile çalıştır; yeni kütüphaneler (`webauthn`) sadece orada kurulu. Tarayıcıda eski giriş unutulacak, karşına yeni kayıt ekranı çıkacak; Windows Hello ile hesap aç.

---

## 16 Ekim 2026 (2. oturum) — Faz 0'ın kalanı

Faz 0'ın çıkış kriteri: "CI yeşil; mock'larla uçtan uca sohbet çalışıyor". Eksikler tamamlandı, **tek istisna gerçek giriş (passkey + MFA)**: hangi çözümün kullanılacağı senin kararın (aşağıda açık sorular).

### Ne yapıldı (4 commit)

1. **Sağlayıcı arayüzleri tamamlandı.** Önce sadece `LLMProvider` (model) vardı. Şimdi CLAUDE.md §4.2'deki 9 arayüzün hepsi var: konuşma→metin (STT), metin→ses (TTS), ses klonu, yüz avatarı, avatar kaydı, embedding, moderasyon, e-posta/SMS. Her birinin ücretsiz, internetsiz bir **mock**'u var. Hangisinin kullanılacağı `config/providers.yaml`'dan seçiliyor.
2. **Sözleşme testleri.** `backend/tests/test_provider_contracts.py`: her arayüz için "bir adaptör bunu yapabilmeli" testleri. İleride ElevenLabs ya da kendi sunucumuz eklenince aynı testlerden otomatik geçecek.
3. **Ana sayfadaki sahte veriler kaldırıldı.** "Ruh halin: İyi" ve "1.2 saat" kartları uydurmaydı. Ruh hali kartı artık dürüstçe "Yakında" diyor; kullanım kartı tamamen kalktı (ayrıca "günde 2 saat kullan" önerisi, EVA'nın bağımlılık yaratmama kuralına da ters düşüyordu). Hiçbir işe yaramayan bildirim zili de kalktı.
4. **CI kuruldu** (`.github/workflows/ci.yml`). GitHub'a her push'ta otomatik olarak: lint, tip kontrolü, testler, migration'ların gerçek Postgres'te çalışması, frontend build'i, bağımlılık güvenlik taraması, OpenAPI uyumu ve sızmış anahtar taraması (gitleaks).
5. **Gözlemlenebilirlik.** Her sohbet turunda "ilk kelime ne kadar sürdü" ve "toplam ne kadar sürdü" artık OpenTelemetry metriği olarak ölçülüyor. Hata takibi için Sentry eklendi; ikisi de varsayılan olarak kapalı, açıldığında bile mesaj içeriği ve kişisel veri dışarı gitmiyor (testle kontrol ediliyor).
6. **Gizli bir hata bulundu ve düzeltildi.** Windows'ta saat ~15 ms adımlarla ilerliyor. Senin mesajın ile EVA'nın cevabı aynı zaman damgasını alınca sohbet geçmişinin sırası karışabiliyordu. Artık her mesaj bir öncekinden kesinlikle sonra kaydediliyor.

Ayrıca: Prettier (kod biçimlendirici) frontend'e eklendi, `frontend/.env.local.example` yanlışlıkla git dışında kalmıştı, eklendi.

**Testler:** 25 → 41, hepsi geçiyor. Lint, tip kontrolü, frontend build temiz. API 8011 portunda gerçekten çalıştırılıp mock ile uçtan uca sohbet denendi.

### Senin yapman gereken

- **CI'ı görmek için push:** `git push -u origin phase-0-skeleton`, sonra GitHub'da "Actions" sekmesi.
- **İsteğe bağlı, commit öncesi anahtar taraması:** `uvx pre-commit install` (bir kere).

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
- ~~**Ana sayfadaki bazı kartlar sahte.**~~ 2. oturumda temizlendi.
- **"Yakında" yazan her yer:** sesli görüşme, görüntülü görüşme, anılar, Miras, Karakter Stüdyosu, analiz, keşfet, profil.
- **Gerçek giriş yok.** Passkey ve MFA için karar bekleniyor.
- **Docker yok.** Postgres yerine geçici olarak SQLite kullanılıyor.
- ~~**CI yok.**~~ 2. oturumda kuruldu.

---

## Nasıl çalıştırılır

Önce eski terminalde açık kalan uvicorn varsa Ctrl+C ile kapat (8000 portunu tutuyor).

**Terminal 1 — backend:**
```powershell
cd C:\Users\HYPER\Desktop\EVA\backend
uv run alembic upgrade head      # yeni migration varsa veritabanını günceller
uv run uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend:**
```powershell
cd C:\Users\HYPER\Desktop\EVA\frontend
npm run dev
```

Tarayıcıda `http://localhost:3000` aç. API'yi denemek için `http://localhost:8000/docs`.

**Testler ve kontroller:**
```powershell
cd backend
uv run pytest                 # testler
uv run ruff check .           # lint
uv run mypy app tests         # tip kontrolü
cd ..rontend
npm run lint; npm run typecheck; npm run format:check
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
- **Passkey:** Şifresiz giriş. Cihazın bir anahtar çifti üretir; gizli olan yarısı cihazdan hiç çıkmaz, sunucu sadece açık yarısını saklar. Girişte cihaz parmak izi/PIN ile kilidi açıp imza atar.
- **WebAuthn:** Tarayıcıların passkey için kullandığı standart.
- **Challenge:** Sunucunun her girişte ürettiği tek kullanımlık rastgele sayı. Cihaz onu imzalar; böylece eski bir imza tekrar kullanılamaz.
- **RP ID:** Passkey'in bağlı olduğu alan adı (şu an `localhost`). Sahte bir sitede passkey çalışmaz çünkü alan adı tutmaz.
- **Tehdit modeli (threat model):** "Saldırgan neler deneyebilir, nasıl engelliyoruz, hangi test kanıtlıyor" tablosu. `docs/threat-model.md`.
- **CI (Continuous Integration):** Her push'ta GitHub'ın kodu kendi makinesinde test etmesi. Bir şey bozulursa kırmızı olur.
- **Sözleşme testi (contract test):** Bir arayüzün "olmazsa olmaz" davranışlarını test eder. Her yeni adaptör aynı testlerden geçmek zorunda.
- **STT / TTS:** Speech-to-text (konuşmayı yazıya çevirme) / text-to-speech (yazıyı sese çevirme).
- **Embedding:** Bir metni anlamını temsil eden sayı listesine çevirmek. Benzer anıları bulmak için kullanılacak (Faz 1).
- **OpenTelemetry:** Hız ölçümlerini (metrik) ve bir isteğin yolculuğunu (trace/span) standart biçimde toplayan araç.
- **Sentry:** Sunucuda oluşan hataları toplayıp gösteren servis.
- **gitleaks:** Kodda yanlışlıkla bırakılmış API anahtarı arayan tarayıcı.
- **Prettier:** Kod biçimlendirici; herkesin kodu aynı görünür.

---

## Açık sorular (sonraki oturum)

1. EVA için hangi API anahtarı? Anthropic mi, Groq adaptörü mü yazılsın?
2. Docker Desktop kurulacak mı, yoksa bir süre SQLite ile mi devam?
3. Platform önceliği: önce web mi, mobil (Expo) da başlasın mı?

## Sıradaki adım önerisi

1. Girişin kalan parçaları: yedek giriş (TOTP + kurtarma kodları), güvenli oturum, step-up, cihaz ekranı.
2. EVA'yı gerçek modele bağlamak (API anahtarı).
3. Faz 1: hafıza ve anılar, "EVA ne biliyor" ekranı.

Bundan sonra daha küçük adımlarla ilerleyip her adımda yeni kavramları açıklayacağız.
