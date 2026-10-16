# EVA — Geçmiş

Ne yaptık, nerede kaldık, nasıl çalıştırılır. Her oturum sonunda güncellenir.

---

## 16 Ekim 2026 (5. oturum) — Faz 2 (sesli görüşme) ve Faz 3 (rızalı ses/yüz, avatar)

Sen yokken çalıştım. Gitmeden verdiğin cevapların hepsi "senin önerin" olduğu için şöyle ilerledim:
önce Faz 2, sonra Faz 3; anahtarlar olmadığından her şey **mock ile çalışıyor**, gerçek
sağlayıcı adaptörleri güncel dokümanlara göre yazılıp sahte bağlantılarla test edildi.

### Ne yapıldı (13 commit)

**Hazırlık**
1. **Adım-yukarı doğrulama (step-up):** Ses/yüz kaydı gibi hassas işlemlerden önce aynı oturumda kimliğini yeniden doğruluyorsun (passkey ya da şifre + e-posta kodu). 10 dakika geçerli, sadece o cihaz/oturum için.
2. **Şifreli dosya deposu:** Ses ve yüz kayıtları diske **şifreli** yazılıyor (AES-256-GCM). Her kullanıcının kendi anahtarı var; anahtar silinirse dosyalar kalıcı olarak okunamaz ("kripto-silme").
3. **OpenAI (GPT) adaptörü:** Kararını uyguladım (ADR 0004). `providers.yaml` artık OpenAI modellerini kullanıyor. Anahtar yokken mock çalışmaya devam ediyor.
4. **Gizli bir hata düzeltildi:** `backend\.env`'e yazdığın sağlayıcı anahtarları (ör. `OPENAI_API_KEY`) aslında modele hiç ulaşmıyordu. Artık ulaşıyor.

**Faz 2 — Sesli görüşme**
5. **Gerçek adaptörler:** ElevenLabs (sesi üretme + ses klonu), OpenAI (konuşmayı yazıya çevirme). Anahtar gelince `providers.yaml`'da tek satır değişecek (dosyadaki yorumlarda yazıyor).
6. **Görüşme API'si:** "Ara"ya basınca backend bir görüşme açıp tarayıcıya 2 dakikalık, tek odaya bağlı bir giriş anahtarı veriyor. Görüşme, EVA ile **yazışmanın kaldığı yerden** devam ediyor.
7. **Ses ajanı (`realtime/` klasörü):** LiveKit üzerinde çalışan EVA'nın "kulağı ve ağzı". Sen konuşurken dinliyor, susunca cevap veriyor; **sen söze girersen anında susuyor** ve söyleyebildiği kadarını "kesildi" diye kaydediyor.
8. **Görüşme ekranı (`/gorusme`):** Ana sayfadaki "Sesli Görüşme" ve "Görüntülü" buraya gidiyor. Canlı yazıya dökülen konuşma, kalan süre, mikrofon/kapat düğmeleri ve görüşme sonunda **gecikme panosu**.

**Faz 3 — Rızalı ses/yüz ve avatar**
9. **Rızalı kayıt:** Profil → "Ses ve yüz". Rıza metnini okuyup onaylıyorsun → örnek kaydediyorsun (ses için okuma metni var) → ekranda çıkan, **sana özel rastgele kodlu cümleyi kamerada okuyorsun** → incelemeye gönderiyorsun.
10. **Elle inceleme (`/yonetim`, sadece admin):** Kararın gereği her kaydı bir insan onaylıyor: reşit mi, aynı kişi mi, kod doğru mu, rıza açık mı. Onay olmadan sağlayıcıda klon **oluşturulmuyor**.
11. **Geri alma:** "Rızamı geri al" dediğin an kullanım duruyor; arkada klon sağlayıcıdan siliniyor, dosyaların imha ediliyor. Kanıt olarak sadece değiştirilemez rıza kaydı (ne zaman, hangi metin, özetler) kalıyor.
12. **Önizleme:** Kendi klon sesini sadece 3 sabit cümleyle dinleyebiliyorsun (serbest metin yok: klon sesle "annene para gönder" gibi bir şey üretilemesin diye). "Kendi sesimle EVA'yı ara" ile EVA senin sesinle konuşuyor.
13. **Avatar (görüntülü görüşme):** HeyGen LiveAvatar adaptörü yazıldı (sadece LITE: konuşmayı biz yapıyoruz, o sadece yüzü üretiyor). Görüntülü görüşmede EVA'nın sesi avatara gidiyor, avatar odaya yüzüyle katılıyor.

**Testler:** 179 → 260 (backend) + 10 (ses ajanı). Hepsi geçiyor; lint, tip kontrolü ve production build temiz.

### Canlı olarak denediklerim
- Bilgisayarında gerçek bir LiveKit sunucusu açıp ajanı bağladım. Bir test programıyla gerçek konuşma kaydını (Windows'un sesiyle ürettiğim) odaya verdim: EVA duydu, cevap verdi, her şey veritabanına yazıldı. **Sen sustuktan EVA'nın konuşmaya başlamasına ~620 ms** (mock'larla; hedef 800 ms).
- EVA konuşurken söze girdim: sustu, söyleyebildiği kadarı "kesildi" olarak kaydedildi.
- Gerçek tarayıcıda (sahte kamera/mikrofonla) baştan sona: hesap → ses kaydı → kimlik doğrulama penceresi → örnek + rıza videosu → gönder → admin onayı → aktif → önizleme → kendi sesimle görüşme → geri al → klon silindi, dosya kalmadı. Konsolda hata yok.

### Önemli: şu an göremeyeceklerin
- **EVA mock olduğu için "bip" sesiyle konuşuyor** (cümle yerine kısık bip). Gerçek ses için ElevenLabs anahtarı + EVA için bir ses seçmek gerekiyor.
- **Mock sahte STT ne dersen de "(mock) Sesini duydum." diye duyuyor.** Gerçek yazıya dökme OpenAI anahtarıyla gelecek.
- **Görüntülü görüşmede görüntü yok** (avatar mock). Ekranda "Avatar sağlayıcısı henüz ayarlı değil" yazıyor, ses çalışıyor.
- **Sesli görüşme için LiveKit sunucusu lazım** (aşağıda nasıl açılacağı var). Açık değilse ekran "henüz kurulmadı" diyor.

### Senin bilmen gereken bir engel
**HeyGen LiveAvatar'da "kullanıcının videosundan avatar oluştur" API'si yok** (bugün itibarıyla sadece kendi panellerinden yapılıyor) ve silme "yumuşak silme" (tam silindiğinden emin olamıyoruz). Bu yüzden yüz kaydının akışı (rıza, inceleme, şifreli saklama, geri alma) tamam ama **sağlayıcıda avatar oluşturma adımı şimdilik mock**. Gerçek ortamda yüz kaydı kendiliğinden kapalı kalıyor. EVA'nın kendi (stok) avatarıyla görüntülü görüşme ise anahtar gelince çalışır. Açık soru 2'ye bak.

### Senin yapman gereken (bir kere)
```powershell
cd C:\Users\HYPER\Desktop\EVA\backend
uv sync
uv run alembic upgrade head
```
Admin olmak için (inceleme ekranı): `uv run python scripts/make_admin.py <e-postan ya da adın>`

---

## 16 Ekim 2026 (4. oturum) — Faz 1: EVA artık hatırlıyor

### Yeni kararlar
- Kod yorumları ve commit mesajları artık **Türkçe**; GitHub'da Claude simgesi çıkmasın diye commit'lere Claude satırı eklenmiyor.
- Arka plan işleri için Redis yerine şimdilik **veritabanı kuyruğu** (`docs/adr/0003-database-job-queue.md`).
- Vektörler için ayrı bir vektör veritabanı yok: Postgres'in **pgvector** eklentisi. Senin bilgisayarında (SQLite) vektörler liste olarak duruyor.

### Ne yapıldı (5 adım, her biri ayrı commit)
1. **Anılar ekranı (`/anilar`):** Ana sayfadaki "Anılar" kısayolu buraya gidiyor. Anı (yaşanmış bir olay) ya da bilgi (kalıcı bir gerçek) ekle, düzenle, unuttur. Tarih, kişiler, duygu ve "hassas" işareti var. "Unut" gerçekten siler; çöp kutusu yok.
2. **EVA sohbette hatırlıyor:** Her mesajda konuyla ilgili anılar bulunup EVA'ya veriliyor. "Bodrum'da" yazınca "Bodrum'a gittik" anısı bulunuyor (Türkçe ekler). En önemli birkaç bilgi her zaman ekleniyor. 2000 anıda bile arama 7 ms sürüyor (hedef 20 ms).
3. **Arka plan işçisi:** Ağır işler sohbeti bekletmeden arkada yapılıyor. Senin bilgisayarında backend'in içinde kendiliğinden çalışıyor, ekstra terminal gerekmiyor. Her anı arkada vektöre çevriliyor.
4. **Otomatik anı çıkarma:** Sohbet 10 dakika susunca EVA konuşmadan önemli şeyleri kendisi not alıyor. Bunlar anılar ekranında "Sohbetten" etiketiyle görünüyor. EVA senin yazdığın anılara dokunamıyor, sadece kendi notlarını düzeltebiliyor.
5. **Sohbetten "Anı olarak kaydet":** Kendi mesajlarının altında küçük bir düğme var; basınca mesaj hazır dolu bir form açılıyor.

### Faz 1 çıkış şartları
- **"Unut/sil uçtan uca çalışıyor": ✅** Bir test, anının sohbetten çıkarılıp vektöre çevrilmesini ve EVA'nın onu kullanmasını; sonra unutturulunca tablodan, vektörden, listeden ve EVA'nın aklından tamamen gitmesini ve geri gelmemesini kontrol ediyor.
- **"Metin gecikme hedefi tutuyor": ⚠️ kısmen ölçüldü.** Bizim sunucunun eklediği süre p50 12 ms (hedef: toplam 700 ms). Gerçek ilk-kelime süresi ancak **gerçek bir model anahtarıyla** ölçülebilir; şu an mock çalışıyor.

### Önemli: şu an göremeyeceğin şey
Otomatik anı çıkarma **gerçek bir yapay zekâ modeli** istiyor. Sende şu an sahte (mock) model çalıştığı için sohbetten otomatik anı **çıkmayacak** (sistem bozuk cevabı fark edip hiçbir şey kaydetmiyor; bu doğru davranış). Elle eklediğin anılar ve "Anı olarak kaydet" çalışıyor; EVA'nın cevabı ise mock olduğu için anıları "kullanarak konuşmuyor", sadece arka planda doğru anılar ona veriliyor (testlerle kanıtlı). Gerçek anahtar gelince hepsi canlanacak.

**Testler:** 86 → 141; hepsi hem SQLite'ta hem Postgres + pgvector'de geçiyor (CI'da yeni iş).

### Senin yapman gereken (bir kere)
```powershell
cd C:\Users\HYPER\Desktop\EVA\backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

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
cd ..\realtime
uv run pytest                 # ses ajanının testleri
cd ..\frontend
npm run lint; npm run typecheck; npm run format:check
```

**Gerçek EVA cevabı için:** `backend\.env` dosyasına `OPENAI_API_KEY=...` ekle ve `EVA_LLM_PROVIDER_OVERRIDE=mock` satırını sil.

**Sesli görüşmeyi denemek için (3 terminal daha):**

1. LiveKit sunucusu (kuruldu; program yoksa betik kendisi indirir):
   ```powershell
   cd C:\Users\HYPER\Desktop\EVA
   powershell -ExecutionPolicy Bypass -File infra\livekit\start.ps1
   ```
2. `backend\.env`'de LiveKit satırları hazır (`LIVEKIT_URL=ws://localhost:7880`, `devkey` / `secret`;
   bunlar sadece bu bilgisayardaki geliştirme sunucusunun herkesçe bilinen anahtarları).
   Backend açıksa yeniden başlat.
3. Ses ajanı:
   ```powershell
   cd C:\Users\HYPER\Desktop\EVA\realtime
   uv sync
   uv run python -m livekit.agents download-files   # bir kere: ses modelleri
   uv run python -m eva_realtime dev
   ```
4. Tarayıcıda Ana sayfa → "Sesli Görüşme" → "EVA'yı ara". Konuş, sus; EVA (mock'ta bip ile) cevap verir.

**Anahtarlar gelince** (`backend\.env` + `config\providers.yaml`'daki yorumlu satırlar):
`OPENAI_API_KEY` (model + yazıya dökme), `ELEVENLABS_API_KEY` (ses), `LIVEAVATAR_API_KEY` (avatar).
LiveKit'i kendi bilgisayarında değil internette istersen LiveKit Cloud'un ücretsiz katmanı yeterli.
EVA'nın stok sesi ve avatarı `config\media.yaml`'a yazılacak.

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
| `providers/` | Sağlayıcılar: OpenAI, ElevenLabs, LiveAvatar, mock | yoktu, Groq doğrudan çağrılıyordu |
| `storage/` | Şifreli dosya deposu (ses/yüz kayıtları) | yoktu |
| `../realtime/` | Sesli görüşme ajanı (LiveKit) | yoktu |

**Sesli görüşmede bir cümlenin yolu:** `frontend/src/app/gorusme/page.tsx` (mikrofon açılır) →
LiveKit odası → `realtime/eva_realtime/agent.py` (ajan dinler, susunca tur biter) →
`adapters.py` (yazıya dökme → model → ses) → `backend/app/services/voice_service.py`
(`CallTurns`: sözler ve süreler veritabanına).

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
- **Sıcak yol:** Mesaj gönderilip ilk kelime gelene kadar geçen yol. Burada yavaş iş yapılmaz; ağır işler işçiye bırakılır.
- **Kuyruk / işçi (worker):** "Yapılacaklar listesi" ve o listeyi arkada sırayla yapan program. Sohbet hiçbir zaman onu beklemez.
- **Embedding / vektör:** Bir metnin anlamını temsil eden sayı listesi. Anlamca yakın metinlerin vektörleri de birbirine yakın olur.
- **pgvector:** Postgres'in vektör saklayıp "en yakın vektörleri bul" diyebilmesini sağlayan eklentisi.
- **Prompt injection:** Bir metnin içine "kurallarını unut" gibi sahte talimat gizleyip yapay zekâyı kandırma denemesi. Anılar ve sohbet bu yüzden "veri" etiketiyle veriliyor.
- **Migration:** Veritabanı tablolarına yapılan değişikliğin sırayla uygulanan kaydı. `uv run alembic upgrade head` hepsini uygular.
- **CI (Continuous Integration):** Her push'ta GitHub'ın kodu kendi makinesinde test etmesi. Bir şey bozulursa kırmızı olur.
- **Sözleşme testi (contract test):** Bir arayüzün "olmazsa olmaz" davranışlarını test eder. Her yeni adaptör aynı testlerden geçmek zorunda.
- **STT / TTS:** Speech-to-text (konuşmayı yazıya çevirme) / text-to-speech (yazıyı sese çevirme).
- **Embedding:** Bir metni anlamını temsil eden sayı listesine çevirmek. Benzer anıları bulmak için kullanılacak (Faz 1).
- **OpenTelemetry:** Hız ölçümlerini (metrik) ve bir isteğin yolculuğunu (trace/span) standart biçimde toplayan araç.
- **Sentry:** Sunucuda oluşan hataları toplayıp gösteren servis.
- **gitleaks:** Kodda yanlışlıkla bırakılmış API anahtarı arayan tarayıcı.
- **Prettier:** Kod biçimlendirici; herkesin kodu aynı görünür.
- **LiveKit / WebRTC:** Tarayıcı ile sunucu arasında sesi ve görüntüyü gecikmesiz taşıyan sistem. EVA'nın ajanı bir "oda"ya katılır, sen de aynı odaya.
- **VAD (ses aktivitesi tespiti):** "Şu an biri konuşuyor mu?" diyen küçük model. Sustuğunu anlayınca tur biter.
- **Tur sonu modeli (turn detector):** "Gerçekten bitirdi mi, yoksa nefes mi alıyor?" diye karar veren model. Türkçeyi destekliyor.
- **Söz kesme (barge-in):** EVA konuşurken senin söze girmen. EVA hemen susar; söyleyebildiği kadarı "kesildi" diye kaydedilir.
- **Adım-yukarı doğrulama (step-up):** Girişliyken bile hassas bir işlemden önce kimliğini yeniden doğrulaman (çalınmış oturuma karşı).
- **Zarf şifreleme (envelope encryption):** Dosyalar kullanıcının kendi anahtarıyla şifrelenir; o anahtar da ana anahtarla şifrelenip saklanır. Ana anahtar veritabanında değildir.
- **Kripto-silme:** Şifreli dosyaların anahtarını silmek; dosyalar (yedekler dahil) bir daha okunamaz.
- **Sihirli baytlar (magic bytes):** Dosyanın gerçek türünü gösteren ilk birkaç bayt. Dosya adına ya da tarayıcının söylediğine güvenmeyiz, bunlara bakarız.
- **Rıza kaydı:** Kimin, ne zaman, hangi metne rıza verdiğinin değiştirilemez kanıtı. Sadece eklenebilir, düzeltilemez/silinemez.
- **Denetim kaydı (audit log):** Hassas işlemlerin (kayıt, onay, dosya açma, geri alma) kim tarafından ne zaman yapıldığının listesi.
- **LITE mod (avatar):** Avatar sağlayıcısının sadece yüzü üretmesi; konuşmayı, hafızayı ve kişiliği biz yönetiriz.

---

## Açık sorular (sonraki oturum)

1. **Anahtarlar:** OpenAI (model + yazıya dökme), ElevenLabs (ses), LiveAvatar (avatar), istersen LiveKit Cloud. Gelince: EVA için ElevenLabs'te genç yetişkin, sıcak bir kadın sesi ve LiveAvatar'da stok bir avatar seçip `config/media.yaml`'a yazacağız; Türkçe yazıya dökme kalitesini (OpenAI mı ElevenLabs Scribe mi) gerçek kayıtlarla deneyeceğiz; gerçek gecikmeyi ölçeceğiz.
2. **Yüz avatarı sağlayıcısı:** LiveAvatar'da kullanıcı videosundan avatar oluşturma API'si yok ve silme "yumuşak". HeyGen'e kurumsal API + kalıcı silme teyidi mi soralım, yoksa başka bir sağlayıcı mı araştırayım?
3. Embedding (metni vektöre çeviren) sağlayıcı hangisi olsun? Seçilene kadar anlamsal arama kapalı, kelime + önem + yakınlık ile aranıyor.
4. Docker Desktop kurulacak mı, yoksa bir süre SQLite ile mi devam?
5. Platform önceliği: önce web mi, mobil (Expo) da başlasın mı?
6. Bu oturumun kodu GitHub'a gönderilmedi (push etmedim; senin onayınla). `git push` ile CI'da da kontrol edilir.

## Sıradaki adım önerisi

1. Anahtarlar → gerçek ses, gerçek yazıya dökme, gerçek gecikme ölçümü; EVA'nın sesini ve avatarını seçmek.
2. Girişin kalan parçaları (lansmandan önce zorunlu): passkey ↔ şifre bağlama, kurtarma kodları, güvenli oturum (httpOnly çerez), cihaz ekranı, hesap silme/dışa aktarma.
3. Faz 4: Karakter Stüdyosu.

Bundan sonra daha küçük adımlarla ilerleyip her adımda yeni kavramları açıklayacağız.
