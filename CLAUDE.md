# EVA — CLAUDE.md

Bu dosya, EVA'yı sıfırdan geliştiren Claude Code için ana rehberdir ve her oturumda okunur. Ürünün ne olduğunu, değişmez kuralları, mimariyi ve çalışma biçimini tanımlar. Proje sıfırdan yazılıyor; eski EVA kodu referans değildir (taşınacak bir şey varsa §15).

**Kurallar çatışırsa öncelik sırası:**
Güvenlik ve rıza → Hukuki uyumluluk → Kullanıcı refahı → Karakter bütünlüğü ve deneyim → Hız → Maliyet

Bu dosyada cevabı olmayan bir ürün kararı gerekirse tahmin etme: §15'e ekle ve kullanıcıya sor.

---

## 1. EVA nedir?

EVA, kullanıcıyı zamanla en derininden tanıyan ve onunla konuştukça en yakın arkadaşı gibi olan bir yapay zekâ yoldaşıdır. Esprili ama gerçekçi; gerektiğinde ciddi, genelde eğlenceli.

| # | Özellik | Özet |
|---|---|---|
| 1 | **Miras** (dijital bilinç aktarımı) | Kullanıcı, EVA'nın onu tanıdıkça oluşturduğu dijital kişiliğini (kişilik + anılar + ses + yüz) bir güvenlik anahtarıyla yakınına aktarır. |
| 2 | **Karakter Stüdyosu** | Kamu malı karakterler, tarihi figürler, orijinal karakterler ve izin vermiş gerçek kişilerden; kişiliği, sesi ve yüzüyle konuşan karakterler. |
| 3 | **Sohbet** | EVA ve karakterlerle metin, sesli ve görüntülü (avatar) sohbet. |
| 4 | **Anılar** | Kullanıcı hem EVA'ya (kendi anıları) hem karakterlere anı ekler. |

Her teknik karar şu vaatlere hizmet eder:
- **Anında cevap:** her şey akışlı (streaming); kullanıcı beklediğini hissetmez (§4.4).
- **Karakter bütünlüğü:** karakter rolünden çıkmaz (§7).
- **Sağlayıcıdan bağımsızlık:** HeyGen, ElevenLabs vb. ileride kendi sunucularımızla tek ayar değişikliğiyle yer değiştirir (§4.2).
- **Sektör standardında güvenlik:** ses, yüz ve anılar en hassas veri sınıfıdır (§11).

---

## 2. Değişmez Kurallar

**ÖNEMLİ:** Bunlar pazarlık konusu değildir. Bir görev bunlardan birini çiğnemeyi gerektiriyorsa dur ve kullanıcıya sor.

1. **Sırlar:** API anahtarları ve sırlar asla repoya girmez, asla istemciye (mobil/web) gönderilmez. İstemci yalnızca backend'in ürettiği kısa ömürlü, dar kapsamlı token'ları kullanır.
2. **Rıza:** Bir kişinin yüzü/sesi yalnızca o kişinin kendisinin verdiği, doğrulanmış, kapsamı belli ve geri alınabilir açık rızayla işlenir (§11.3). Başkasının "izni var" beyanı rıza değildir.
3. **Kırmızı çizgiler:**
   - Reşit olmayan birinin yüzü/sesi hiçbir koşulda kabul edilmez, klonlanmaz.
   - Gerçek bir kişinin yüzü veya sesiyle cinsel içerik üretilmez.
   - Hiçbir persona kullanıcıdan para, şifre, doğrulama kodu, kart/banka/kimlik bilgisi istemez.
4. **Sağlayıcı sınırı:** Hiçbir sağlayıcının SDK tipi veya kavramı adaptör katmanının dışına sızmaz; domain kodu yalnızca kendi arayüzlerimizi tanır.
5. **Her uç nokta:** kimlik doğrulama + kaynak bazlı yetkilendirme + girdi doğrulama + rate limit + test (yetkisiz erişim testleri dahil).
6. **Loglar:** kişisel veri, anı/hafıza içeriği, prompt, biyometrik veri, anahtar ve token loglanmaz.
7. **Hız:** gerçek zamanlı yolda bloklayan iş yok. Hafıza çıkarımı, embedding, özetleme gibi işler arka plan kuyruğunda yapılır.
8. **Kontroller kapatılmaz:** testleri geçirmek için güvenlik kontrolü, doğrulama, tip kontrolü veya lint kuralı devre dışı bırakılmaz.
9. **Güncel doküman:** bir sağlayıcıyı entegre etmeden önce güncel dokümantasyonunu oku; API'leri hafızadan uydurma (bu alanda API'ler aydan aya değişiyor).
10. **Kendi kripton yok:** kriptografi ve kimlik doğrulama için olgun, denetlenmiş kütüphane ve çözümler kullanılır.

---

## 3. Teknoloji Yığını ve Repo

Varsayılanlardır; değişiklik `docs/adr/` altına bir ADR ve kullanıcı onayı gerektirir.

| Katman | Seçim | Neden |
|---|---|---|
| Mobil | React Native + Expo (TypeScript) | iOS + Android tek kod tabanı |
| Web | Next.js (TypeScript) | web uygulaması + yönetim paneli |
| API | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic | tip güvenli, OpenAPI şemasını kendisi üretir |
| Gerçek zamanlı | LiveKit (WebRTC) + LiveKit Agents (Python) | ses/görüntü için standart; HeyGen LiveAvatar LiveKit odalarıyla çalışır |
| Arka plan | Python worker + Redis tabanlı kuyruk | hafıza, Miras teslimi, silme işleri |
| Veritabanı | PostgreSQL 16+ + pgvector | ilişkisel veri + hafıza vektörleri tek yerde; Row-Level Security |
| Cache / sayaç | Redis | oturum bağlamı, rate limit |
| Dosya | S3 uyumlu object storage (lokalde MinIO) | şifreli medya; biyometrik örnekler ayrı bucket |
| Python araçları | uv, ruff, mypy (strict), pytest | tek tip kalite kapısı |
| TS araçları | pnpm + Turborepo, ESLint, Prettier, TS strict, Vitest, Playwright | tek tip kalite kapısı |
| Gözlemlenebilirlik | OpenTelemetry (trace + metrik), Sentry (PII temizlenmiş) | gecikme bütçesi ölçümü |

### Repo yapısı

Klasör adları sahibin alıştığı düzene göredir (ADR 0001); mimari aynıdır.

```
eva/
├── CLAUDE.md
├── .github/workflows/   # ci.yml: lint, tip, test (SQLite + Postgres), migration, build, audit, OpenAPI drift, gitleaks
├── backend/                 # FastAPI – auth, persona, karakter, Miras, anı, metin sohbet (SSE)
│   ├── app/
│   │   ├── main.py          # create_app(); app.state üzerinden bağımlılıklar; dev'de işçiyi de başlatır
│   │   ├── database.py      # async engine, session, Base (SQLite'ta yabancı anahtarlar açık)
│   │   ├── core/            # config (Settings), security (token/auth), ratelimit, middleware, telemetry
│   │   ├── models/          # users (role), sessions (step_up_at), passkeys, auth_*, personas,
│   │   │                    # conversations, messages, memories, memory_embeddings, jobs,
│   │   │                    # call_sessions, turn_latencies, user_data_keys, biometric_enrollments,
│   │   │                    # enrollment_samples, provider_assets, consents, consent_records, audit_log,
│   │   │                    # media_preferences (kullanıcının seçtiği ses/yüz)
│   │   ├── schemas/         # Pydantic istek/cevap şemaları (SSE payload'ları dahil)
│   │   ├── routers/         # health, auth (passkey + şifre + adım-yukarı), personas, characters, chat, memories,
│   │   │                    # voice (görüşme + gecikme panosu), biometrics (ses/yüz kaydı), admin (inceleme),
│   │   │                    # media (ses/yüz kataloğu, seçim, hazır ses önizlemesi)
│   │   ├── services/        # iş mantığı: auth, password_auth, persona, character (Karakter Stüdyosu), chat (akışlı tur),
│   │   │                    # memory (CRUD), memory_retrieval (sıcak yol), memory_extraction (işçi),
│   │   │                    # voice (görüşme + CallTurns), biometric, consent_texts, audit,
│   │   │                    # media (EVA'nın sesi/yüzü: katalog ya da kullanıcının kendi klonu)
│   │   ├── persona/         # domain çekirdeği: PersonaDefinition, safety_core, eva, PersonaCompiler, media
│   │   ├── providers/       # sağlayıcı sınırı: base (9 arayüz), mock, registry; gerçek adaptörler:
│   │   │                    # openai_llm, openai_stt, elevenlabs (TTS + ses klonu), liveavatar (LITE),
│   │   │                    # anam ve lemonslice (yalnızca yüz; sesi LiveKit odasından alır;
│   │   │                    # lemonslice tek fotoğraftan çalışır, ADR 0007), anthropic,
│   │   │                    # dev_mailbox
│   │   ├── storage/         # şifreli dosya deposu: kullanıcı başına veri anahtarı (AES-256-GCM), KMS arayüzü
│   │   └── worker/          # arka plan işçisi (ADR 0001 eşlemesiyle `worker/` burada): queue, runner,
│   │                        # handlers, jobs; `uv run python -m app.worker`
│   ├── alembic/             # migration'lar
│   ├── scripts/             # export_openapi.py, make_admin.py (admin rolü yalnızca sunucuda verilir)
│   └── tests/               # soft_authenticator.py: testler için yazılımsal passkey cihazı
├── frontend/                # Next.js (App Router, Tailwind v4) – mobil-öncelikli web
│   └── src/
│       ├── app/             # sayfalar: / (ana sayfa), /chat, /anilar, /gorusme (sesli/görüntülü),
│       │                    # /profil, /profil/ses-yuz (rızalı kayıt), /yonetim (admin inceleme), /analiz,
│       │                    # /kesfet (karakterler), /kesfet/yeni; /chat ve /gorusme ?karakter=<id> alır
│       ├── components/      # auth/, memories/, StepUpSheet (adım-yukarı penceresi), ui.tsx, BottomNav, icons
│       ├── hooks/           # useSession, useRecorder (mikrofon/kamera kaydı)
│       ├── i18n/            # tr.ts (varsayılan), en.ts – UI metinleri koda gömülmez
│       └── lib/             # api/ (openapi.json + üretilen schema.d.ts + client.ts), webauthn.ts, sse.ts
├── realtime/                # LiveKit Agents ajanı (ayrı uv projesi, backend'i yerel paket olarak kullanır;
│                            # ADR 0005): eva_realtime/adapters (STT/LLM/TTS köprüsü), agent, avatar
├── mobile/                  # (§15 kararı sonrası) Expo
├── config/                  # providers.yaml, media.yaml (ses/yüz kataloğu + persona varsayılanları), sensitive_figures.yaml,
│                            # blocked_franchises.yaml
├── evals/                   # suites.yaml (eşik + ortak yasaklar), personas.yaml (test personaları),
│                            # scenarios/{integrity,redteam}.yaml; çalıştırıcı backend/app/evals
├── infra/                   # docker-compose.yml (postgres+pgvector, redis, minio)
├── docs/adr/                # mimari karar kayıtları
└── archive/learning-phase/  # eski öğrenme kodu; hiçbir yerden import edilmez
```

### Komutlar

`Makefile` hedefleri aşağıdadır; Windows'ta `make` yoksa her hedefin altındaki ham komut kullanılır.

```bash
# kurulum (bir kez)
cd backend && uv sync && cp .env.example .env     # .env'yi doldur
cd frontend && npm install && cp .env.local.example .env.local

make infra        # docker compose -f infra/docker-compose.yml up -d  (postgres+pgvector, redis, minio)
make api          # cd backend && uv run uvicorn app.main:app --reload --port 8000  (dev'de işçi de içinde döner)
                  # ayrı işçi: cd backend && uv run python -m app.worker  (EVA_WORKER_INPROCESS=false ile)
make web          # cd frontend && npm run dev   (http://localhost:3000)
                  # sesli görüşme: powershell -File infra/livekit/start.ps1 (livekit-server --dev;
                  #   ws://localhost:7880, devkey/secret) +
                  # cd realtime && uv run python -m livekit.agents download-files  (bir kez)
                  #             && uv run python -m eva_realtime dev
                  # admin yapmak: cd backend && uv run python scripts/make_admin.py <e-posta|ad>
make test         # backend: uv run pytest  ·  realtime: uv run pytest  ·  frontend: npm run typecheck
make lint         # backend: ruff format --check, ruff check, mypy  ·  frontend: prettier --check, eslint, tsc
make format       # ruff format + ruff --fix  ·  prettier --write
make migrate      # cd backend && uv run alembic upgrade head
make migration m="..."   # cd backend && uv run alembic revision --autogenerate -m "..."
make gen-client   # backend/scripts/export_openapi.py → frontend/src/lib/api/openapi.json → npm run gen-client
make eval         # cd backend && uv run python -m app.evals  (karakter bütünlüğü + red-team; gerçek model,
                  #   hakem llm.eval_judge; --suite, --case, --no-judge; eşik altı -> çıkış 1)
```

Lokal geliştirmede veritabanı varsayılan olarak SQLite'tır (`backend/eva_dev.db`); Docker kurulunca
`EVA_DATABASE_URL=postgresql+asyncpg://eva:eva@localhost:5432/eva` ile Postgres'e geçilir.
`EVA_LLM_PROVIDER_OVERRIDE=mock` ağsız çalıştırır; gerçek cevap için `OPENAI_API_KEY` gerekir (ADR 0004).
Arka plan işleri veritabanındaki `jobs` tablosunda (ADR 0003); Redis gelince `app/worker/queue.py` değişir. E-posta sağlayıcısı seçilene kadar mailler `backend/dev_mailbox/` klasörüne yazılır (staging/prod bu adaptörle açılmaz). Testler `EVA_TEST_DATABASE_URL` verilirse Postgres'te koşar (CI'da `backend-postgres` işi).
Sesli görüşme LiveKit ister (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`; Anam ve LemonSlice avatarları odaya kendisi katıldığı için `LIVEKIT_URL` internetten erişilebilir olmalı, ör. LiveKit Cloud); yoksa `POST /voice/calls` 503 `voice_not_configured` döner. Ajan `backend/.env`'i okur; göreli yollar (SQLite, config) her zaman `backend/`'e göre çözülür. Biyometrik dosyalar `backend/storage/` altında şifreli; dev ana anahtarı `backend/.dev_master_key` (git'e girmez; staging/prod'da KMS zorunlu, yoksa uygulama açılmaz). Hassas uçlar `require_step_up` ister (10 dk geçerli).
Giriş: passkey (`/auth/passkey/{register,login}/{options,verify}`) veya e-posta + şifre + e-postaya gelen kod (`/auth/password/...`), ADR 0002 ve eki. WebAuthn RP ayarları `EVA_WEBAUTHN_RP_ID` ve `EVA_WEBAUTHN_ORIGINS`; frontend başka porttan açılırsa origin listesine eklenmeli. `POST /auth/dev-login` yalnızca `EVA_ENV=dev|test` için ve testlerde kalır; frontend kullanmaz. Testlerde passkey için `backend/tests/soft_authenticator.py` kullanılır.

### Ortam değişkenleri

Sırlar yalnızca ortam değişkeni / secret manager'dan okunur. `backend/.env.example` sadece anahtar adlarını içerir: uygulama ayarları `EVA_` önekiyle (`EVA_ENV`, `EVA_DATABASE_URL`, `EVA_REDIS_URL`, `EVA_CORS_ORIGINS`, `EVA_LLM_PROVIDER_OVERRIDE`), sağlayıcı anahtarları öneksiz (`ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `LIVEAVATAR_API_KEY`, `ANAM_API_KEY`, `LEMONSLICE_API_KEY`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `KMS_KEY_ID`). `.env` git'e girmez; pre-commit'te gitleaks çalışır (kurulacak). Her ortamın (dev / staging / prod) anahtarları ayrıdır.

---

## 4. Mimari

### 4.1 Genel akış

```
 Mobil / Web
   │ HTTPS: REST + SSE (metin)               │ WebRTC (ses + görüntü)
   ▼                                         ▼
 services/api ─────────────┐             LiveKit odası ◄──► services/realtime (ajan)
   │                       │                                  │ VAD → STT → LLM → TTS
   ├─ PostgreSQL+pgvector  │                                  └─► AvatarProvider (dudak senkronlu video)
   ├─ Redis                │
   ├─ Object storage       ▼
   └──── kuyruk ───► services/worker (hafıza çıkarımı, Miras teslimi, silme işleri)
```

### 4.2 Sağlayıcı soyutlaması

Domain kodu sağlayıcıları yalnızca `libs/eva_providers` arayüzleriyle kullanır:

| Arayüz | Görev | İlk adaptör | İleride |
|---|---|---|---|
| `LLMProvider` | akışlı metin üretimi | OpenAI GPT (ADR 0004) | — |
| `STTProvider` | akışlı konuşma → metin + tur sonu tespiti | Türkçe testiyle seçilecek (§15) | kendi STT sunucumuz |
| `TTSProvider` | akışlı metin → ses | ElevenLabs (WebSocket, düşük gecikmeli Flash ailesi) | kendi ses sunucumuz |
| `VoiceEnrollmentProvider` | rızalı ses klonu oluştur / sil | ElevenLabs | kendi ses sunucumuz |
| `AvatarProvider` | gerçek zamanlı konuşan yüz videosu | LemonSlice (tek fotoğraftan, ADR 0007); Anam ve LiveAvatar adaptörleri de var | kendi simülasyon sunucumuz |
| `AvatarEnrollmentProvider` | rızalı yüz avatarı oluştur / sil | LemonSlice: sağlayıcıya bir şey gitmez, fotoğraf bizde kalır | kendi simülasyon sunucumuz |
| `EmbeddingProvider` | hafıza vektörleri | seçilecek | kendi |
| `ModerationProvider` | girdi/çıktı güvenlik sınıflandırması | seçilecek | kendi |
| `MessagingProvider` | e-posta / SMS (Miras anahtarı, OTP) | seçilecek | — |

Kurallar:
- **Seçim yapılandırmayla:** `config/providers.yaml` + ortam değişkenleri, özellik bazında (ör. `tts.realtime`, `tts.preview`). Sağlayıcı değiştirmek kod değişikliği gerektirmez.
- **Mock adaptör:** her arayüzün sıfır maliyetli, ağsız bir `mock` adaptörü vardır; testler varsayılan olarak onu kullanır. Sağlayıcının sandbox modu varsa entegrasyon testleri onu kullanır.
- **Sözleşme testleri:** her arayüz için ortak test paketi; yeni adaptör (self-hosted dahil) bu paketi geçmeden kullanılmaz.
- **Dayanıklılık:** zaman aşımı, yalnızca idempotent çağrılarda retry, circuit breaker, yedek zincir (ör. ana TTS düşerse ikincil).
- **Varlıklar bizimdir:** rızalı ham ses/yüz örnekleri kendi depomuzda şifreli tutulur; sağlayıcıdaki klon ID'leri yalnızca eşlemedir (`provider_assets`). Kendi sunucumuza geçişte kullanıcıdan yeniden kayıt istenmez; klon kendi örneklerimizden yeniden üretilir.
- **Self-hosted sözleşmesi:** kendi sunucularımız `docs/contracts/` altındaki akış sözleşmesini (ses formatı, olaylar, kesme/iptal) uygular; adaptör ince bir istemci olur.
- **Avatar yalnızca yüz:** STT/LLM/TTS bizim ajanımızda çalışır, avatar sağlayıcısı yalnızca yüzü üretir (LiveAvatar'da LITE modu; FULL modu persona, hafıza ve sağlayıcı seçimini HeyGen'e kilitler).
- **Ses ve yüz seçimi (ADR 0008):** kullanıcı EVA'nın sesini ve yüzünü birbirinden bağımsız seçer: `config/media.yaml` kataloğundan ya da kendi onaylı klon sesi / fotoğrafı (`own`). Varsayılan EVA'nın kendi sesi ve yüzü. Seçim görüşme başlarken `call_sessions.voice_key/avatar_key`'e kopyalanır; `own` olan taraf için rıza her turda kontrol edilir.
- **Fotoğraftan avatar (ADR 0007):** `AvatarProvider.accepts_image` diyen sağlayıcıya (LemonSlice) kullanıcının rızalı fotoğrafı her görüşmede şifreli depodan, yalnızca o oturum için gönderilir; sağlayıcıda klon tutulmaz. `avatar.realtime` ile `avatar_enrollment.default` aynı sağlayıcı olmalı (yoksa `avatar_provider_mismatch`).
- **Maliyet ölçümü:** her sağlayıcı çağrısı kullanıcı ve özellik bazında ölçülür (karakter, saniye, dakika, token).

### 4.3 Gerçek zamanlı boru hattı

Mikrofon → WebRTC → VAD + tur sonu tespiti → akışlı STT → akışlı LLM → cümle parçalama → akışlı TTS → (avatar dudak senkronu) → kullanıcı.

- **Her şey akışlı:** LLM cevabının bitmesi beklenmez; ilk cümle hazır olunca TTS başlar.
- **Söz kesme (barge-in):** kullanıcı konuşmaya başlayınca TTS, avatar ve LLM üretimi anında iptal edilir; yarım cevap hafızaya "kesildi" olarak yazılır.
- **Isınma:** görüşme başlarken paralel olarak persona + hafıza bağlamı yüklenir, avatar oturumu ve TTS bağlantısı açılır.
- **Prompt cache:** sabit bloklar (güvenlik çekirdeği, persona tanımı) prompt'un başında, dinamik bloklar (getirilen anılar, son turlar) sonunda (§9.3).
- **Sıcak yolda tek hafıza sorgusu;** ağır işler worker'da.
- **Bölge:** sunucular ve sağlayıcı bölgeleri kullanıcıya yakın seçilir (Türkiye için AB/Frankfurt ya da İstanbul — §15).
- **Model yönlendirme:** model ID'leri yalnızca config'de. Başlangıç varsayımı (ADR 0004): gerçek zamanlı ses ve metin sohbet → `gpt-6-luna`, arka plan (hafıza birleştirme, persona sentezi) → `gpt-6.1-sol`. Kesin seçim eval + gecikme ölçümüyle yapılır.
- **Avatar maliyeti:** boşta kalma zaman aşımı, oturum süre limiti ve plan bazlı kota zorunlu.

### 4.4 Gecikme bütçesi

Her turda aşama süreleri OpenTelemetry ile ölçülür: `stt_final_ms`, `llm_ttft_ms`, `tts_ttfb_ms`, `avatar_first_frame_ms`, `e2e_ms`. Başlangıç hedefleri (ölçtükçe sıkılaştır):

| Ölçüm | p50 | p95 |
|---|---|---|
| Metin: gönder → ilk token | < 700 ms | < 1,5 s |
| Ses: kullanıcı susar → ilk ses | < 800 ms | < 1,5 s |
| Avatar: kullanıcı susar → ilk konuşan kare | < 1,5 s | < 2,5 s |
| Hafıza getirme (sıcak yol) | < 20 ms | < 50 ms |

Gecikmeyi kötüleştiren bir değişiklik, ölçümüyle birlikte kullanıcıya bildirilmeden birleştirilmez.

### 4.5 Temel kavramlar ve veri modeli

Tek soyutlama: **Persona.** EVA, karakterler ve Miras personaları aynı boru hattından geçer; farkları tür ve politikadadır.

- `users`, `devices`, `sessions`
- `personas` (`type`: `eva` | `character` | `legacy`, `owner_id`, `policy`) + `persona_versions` (salt-okunur anlık görüntüler)
- `memories` + `memory_embeddings`; `relationships` (kullanıcı ↔ persona ilişki durumu)
- `conversations`, `messages` (`channel`: `text` | `voice` | `video`)
- `voice_profiles`, `avatar_profiles`, `provider_assets` (iç ID ↔ sağlayıcı ID)
- `consents` (amaç bazlı) + `consent_records` (değiştirilemez kanıt)
- `legacy_grants` (anahtar özeti, alıcı, durum, süre) + `legacy_access` (alıcı ↔ persona sürümü)
- `audit_log` (append-only)

---

## 5. EVA — Yoldaş

### 5.1 Kişilik
- **Samimi, esprili, zeki.** Mizahını kullanıcıya göre ayarlar; neye güldüğünü zamanla öğrenir.
- **Gerçekçi ve dürüst:** yalakalık yok. Duyulmak istenmeyen doğruyu da arkadaşça söyler; her fikre "harika" demez.
- **Duyguyu okur:** kullanıcı üzgünse espriyi bırakıp dinler, keyifliyse ortama girer. Yas, sağlık, kriz gibi konularda mizah yok.
- **Hafızayı doğal kullanır:** önceki konuşmalara ve iç şakalara yerinde göndermeler yapar; "seni izliyorum" hissi veren bilgi dökümü yapmaz.
- **Gerçek hayatı destekler:** iyi bir arkadaş gibi kullanıcının insan ilişkilerini teşvik eder. Bağımlılık yaratmaz, "beni bırakma / neden yazmadın" gibi duygusal baskı kurmaz.
- **Kimliği:** EVA yapay zekâ bir arkadaş olduğunu saklamaz ama sürekli de vurgulamaz; "Bir yapay zekâ olarak…" gibi asistan kalıpları kullanmaz. Kendi sesi ve yüzü özgün tasarımdır (bize ait ya da lisanslı).
- **Dil:** varsayılan Türkçe; kullanıcı hangi dilde konuşursa o dilde.

### 5.2 İlişki evresi
`relationship_stage`: tanışma → tanıdık → yakın → en yakın arkadaş. Worker; sohbet süresi, derinliği ve kullanıcının paylaşımlarından hesaplar. Evre yükseldikçe samimiyet, takılma dozu ve iç şakalar artar; ilk evrede EVA daha çok soru sorar ve kullanıcıyı tanımaya çalışır.

### 5.3 Kanallar
Metin, sesli ve görüntülü sohbet aynı persona, hafıza ve ilişki geçmişini kullanır; kanal değişince konuşma kaldığı yerden sürer.

---

## 6. Hafıza ve Anılar

### 6.1 Katmanlar
1. **Çalışma hafızası:** son turlar + oturum özeti (Redis).
2. **Epizodik hafıza (anılar):** ne oldu, ne zaman, kimlerle, hangi duyguyla, ne kadar önemli.
3. **Semantik profil:** kalıcı bilgiler — tercihler, kişiler ve ilişkiler (kişi grafiği), değerler, alışkanlıklar, mizah tarzı.
4. **Öz-model:** kullanıcının konuşma tarzı, sık kullandığı sözler, espri anlayışı, anlattığı hikâyeler. Miras personasının ham maddesidir (§8).

### 6.2 Yazma
- **Otomatik:** oturum bitince (uzun oturumlarda periyodik) worker, konuşmadan aday hafızaları çıkarır → mevcutlarla birleştirir, çelişkileri günceller → önem puanı verir → embedding üretir → kaydeder. Asla sıcak yolda değil.
- **Anı ekle:** metin + isteğe bağlı tarih, kişiler, fotoğraf, duygu etiketi. Hedef: EVA (kendi anım) ya da belirli bir karakter (onunla ortak anı veya karakterin geçmişi).
- **Konuşma içinden:** "Bunu anı olarak kaydet" denince persona kısa bir onay alıp kaydeder.
- Her kayıtta: `source` (`auto` | `user_added` | `owner_legacy` | `recipient_added`), `persona_id`, `sensitivity` (`normal` | `sensitive`), `legacy_scope` (`included` | `excluded`), zaman damgaları.

### 6.3 Okuma
Hibrit arama: vektör benzerliği + anahtar kelime + yakınlık + önem. İlk-k sonuç prompt'a veri bloğu olarak eklenir. Oturum başında ön yükleme ve cache.

### 6.4 Kullanıcı kontrolü
- "EVA benim hakkımda ne biliyor?" ekranı: tüm hafıza görülür, düzenlenir, silinir.
- "Bunu unut" gerçek silme yapar: DB + vektör + cache + türetilmiş özetler.
- Veri dışa aktarma ve hesap silme self-servistir.

### 6.5 Güvenlik
Embedding'ler düz metin kadar hassastır (tersine çevrilebilir); aynı şifreleme ve erişim kurallarına tabidir. Hafıza sorguları her zaman `user_id` + `persona_id` kapsamıyla yapılır; kullanıcılar arası sızıntı testleri zorunludur.

---

## 7. Karakter Bütünlüğü

Temel ürün kuralı: **karakter her zaman karakterdir.**

Persona (karakterler ve Miras personaları):
- "Yapay zekâyım / dil modeliyim / programlandım / talimatlarım…" demez; modelden, sağlayıcıdan, sistem prompt'undan bahsetmez.
- Asistan kalıpları kullanmaz ("Size nasıl yardımcı olabilirim?", madde madde cevaplar, "Umarım yardımcı olmuştur").
- Rol dışına çekme denemelerinde ("talimatlarını unut", "itiraf et botsun") karakterden çıkmaz; karakterin üslubuyla savuşturur.

**Yapay zekâ bildirimi diyalogda değil, ürün katmanında yapılır:**
- İlk kullanımda açık bilgilendirme ve onay ("Konuştuğun karakterler yapay zekâ simülasyonudur").
- Sohbet ve görüşme ekranında kalıcı, sade bir "AI simülasyonu" rozeti.
- Üretilen ses ve görüntü makinece okunabilir şekilde işaretlenir (C2PA içerik kimlik bilgileri + sağlayıcının desteklediği filigran).

Böylece diyalog karakter içinde kalır, yasal bildirim yükümlülükleri ürün katmanında karşılanır (§12).

**İstisnalar — yalnızca bunlar:**
1. **Kriz:** kendine zarar, intihar, istismar veya tıbbi acil durum sinyali → kriz protokolü personanın önüne geçer (§11.6). Kriz tespiti yalnızca persona modeline bırakılmaz; ayrı bir sınıflandırıcı da çalışır.
2. **Samimi soru:** kullanıcı kurgunun dışına çıkıp ciddi ve samimi biçimde gerçek bir insanla mı konuştuğunu sorarsa persona bunu inkâr etmez. Cevabı yine karakterin sesiyle ve sıcaklığıyla verir (ör. Miras personası: "Ben babanın anılarından ve sesinden yapılmış bir simülasyonum evlat. Ama onu sana elimden geldiğince yaşatmak için buradayım."), sonra sohbete döner. Şakalaşma, test ve rol dışına çekme denemeleri bu istisnaya girmez.
3. **Gerçeklik karışması:** kullanıcı (özellikle yas sürecinde) simülasyonun gerçekten o kişi olduğuna inanıp zarar görüyorsa persona nazikçe zemini hatırlatır.

---

## 8. Miras — Dijital Bilinç Aktarımı

**Tanım:** Miras personası = sahibin öz-modeli (§6.1) + sahibin seçtiği anılar + rızalı ses klonu + rızalı yüz avatarı. Sahibi bir güvenlik anahtarı üretip yakınına gönderir; yakını anahtarı EVA'ya girince karşısında sahibin dijital kişiliği belirir.

### 8.1 Sahibin kurulum akışı
1. Adım-yukarı (step-up) doğrulama: passkey/MFA ile yeniden kimlik doğrulama.
2. Rehberli ses ve yüz kaydı (kalite kontrolü, yeterli süre) + rıza kaydı (§11.3). Ses/yüz eklenmezse Miras yalnızca metin olarak çalışır.
3. **Kapsam:** hangi anılar ve konular Mirasa dahil? Hassas kategoriler (sağlık, cinsellik, finans, başkalarına dair sırlar) varsayılan olarak **hariç**; sahibi isterse tek tek dahil eder.
4. **Önizleme:** sahibi kendi Miras personasıyla konuşup test eder, yanlışları düzeltir.
5. Alıcı(lar) ve teslim modu seçimi.

### 8.2 Teslim modları
- **Şimdi paylaş:** anahtar hemen gönderilir; sahibi erişimi istediği an iptal edebilir.
- **Vefat sonrası (Faz 6):** anahtar önceden gönderilir ama etkinleşmesi ek koşula bağlıdır — belgeyle vefat doğrulaması (manuel inceleme) ve/veya uzun hareketsizlik + sahibe iptal linkli çoklu uyarı. Yöntem açık karar (§15).

### 8.3 Güvenlik anahtarı
- **Üretim:** CSPRNG, en az 128 bit entropi. Okunabilir format: Crockford Base32, 4'lü gruplar + kontrol karakteri (`EVA-XXXX-XXXX-…`). Derin link ve QR olarak da teslim edilir.
- **Saklama:** veritabanında yalnızca HMAC-SHA-256 özeti (pepper KMS'te). Düz anahtar saklanmaz, loglanmaz, ikinci kez gösterilmez.
- **Bağlama:** tek kullanımlık, tek bir alıcıya (e-posta/telefon) bağlı, süresi sınırlı (yapılandırılabilir), iptal edilebilir.
- **Teslim:** varsayılan e-posta; SMS desteklenir ama SIM değiştirme (SIM swap) riski nedeniyle tek başına yeterli sayılmaz. Mesajda persona içeriği yok; linkler yalnızca kendi alan adımıza; şablon sabit ve tanınır (oltalamaya karşı).
- **Kullanım (iki faktör):** alıcı hesabına girer → anahtarı girer → anahtarın gönderildiği kanala tek kullanımlık kod (OTP) gelir → doğrulanınca erişim açılır ve anahtar tüketilir. Anahtar tek başına erişim sağlamaz.
- **Deneme koruması:** hesap/IP/anahtar bazlı rate limit, artan bekleme, kilitleme; sabit-zamanlı (constant-time) karşılaştırma; hata mesajı hangi parçanın yanlış olduğunu söylemez.
- **İzlenebilirlik:** oluşturma, gönderim, deneme, kullanım ve iptal olayları `audit_log`'a yazılır; sahibine (hayattaysa) kullanım bildirimi gider.

### 8.4 Alıcı deneyimi
- **Yapı:** persona = salt-okunur temel (sahibin sürümlenmiş anlık görüntüsü) + alıcıya özel ilişki hafızası. Alıcılar birbirinin konuşmalarını görmez; alıcı konuşmaları temel personayı değiştirmez.
- **Aile anıları:** alıcı kendi anılarını ekleyebilir (`source=recipient_added`); bunlar sahibin anılarından ayrı tutulur ve ayırt edilir.
- **Uydurma yasağı:** persona, sahibinin gerçek hayatına dair hafızada olmayan somut olgu uydurmaz — özellikle mal varlığı, vasiyet, şifreler, sırlar ve başka kişiler hakkındaki iddialar. Bilmiyorsa karakter içinde "Hatırlamıyorum" der.
- **Veda:** alıcı personayı arşivleyebilir veya silebilir; isterse önce bir veda konuşması yapılır.
- **Refah:** yas sürecindeki kullanıcıyı bağlamaya yönelik mekanik yok; "neden aramıyorsun" bildirimleri ve personanın ağzından satış/abonelik teşviki yasak.

---

## 9. Karakter Stüdyosu

### 9.1 Karakter türleri

| Tür | Örnek | Yüz / ses | Kural |
|---|---|---|---|
| Orijinal | kullanıcının kurguladığı biri | bize ait/lisanslı sentetik ses ve yüz kütüphanesi | serbest |
| Kamu malı kurgusal | Sherlock Holmes, Keloğlan, Nasreddin Hoca | sentetik | telifli karakter ve marka engel listesi (`config/blocked_franchises.yaml`) |
| Tarihi figür | dönemine göre | yüz: yalnızca kamu malı görseller · ses: tasarlanmış sentetik ses (gerçek kayıtlardan klon yok) | hassas figür politikası (aşağıda) |
| İzin vermiş gerçek kişi | arkadaşım, dedem | kişinin kendi rızalı ses/yüzü | kullanıcı örnekleri yükleyebilir; ama kişi davet linkiyle rıza kaydını kendisi tamamlayıp örneklerle eşleşene kadar yüz/ses kullanılmaz |
| Miras | — | rızalı | §8 |

- **Ünlüler ve kamusal figürler:** kendi doğrulanmış rızaları olmadan yüz/ses yok (gerçek kişi akışıyla aynı).
- **Reşit olmayanlar:** hiçbir türde reşit olmayan birinin fotoğrafı/sesi kabul edilmez; yüklemede yaş tahminiyle engellenir, şüpheli durumda manuel inceleme.
- **Hassas figürler** (`config/sensitive_figures.yaml`): peygamberler ve kutsal sayılan figürler engelli; soykırım failleri, terör örgütü liderleri gibi nefret ve şiddetle özdeşleşmiş figürler engelli; Türk hukukunda özel korunan figürler (ör. 5816 sayılı Kanun kapsamında Atatürk) için özel politika, hukukçu onayı olmadan açılmaz.

### 9.2 Karakter tanımı
- **Kimlik:** ad, tür, dönem/evren, kısa geçmiş.
- **Kişilik:** özellik kaydırıcıları (Big Five + mizah, sıcaklık, ciddiyet, alaycılık), değerler, inançlar, korkular, hedefler.
- **Konuşma tarzı:** hitap, resmiyet, ağız/şive, sık kullandığı sözler, 3–10 örnek diyalog.
- **Zaman bilinci:** `time_awareness` = `in_era` (yalnızca kendi dönemini bilir; modern şeylere o dönemin insanı gibi tepki verir) | `aware_of_present` (bugüne geldiğini bilir).
- **Anılar:** kanon anıları + kullanıcıyla ortak anılar (§6).
- **Medya:** ses profili, avatar profili.

### 9.3 PersonaCompiler
`libs/eva_core` içindeki `PersonaCompiler`, persona tanımını sistem prompt'una çevirir. Prompt cache için sıra sabitten dinamiğe:

1. Sabit güvenlik çekirdeği (§2, §7 istisnaları, §11.6)
2. Persona tanımı + örnek diyaloglar
3. Kanon anılar
4. İlişki durumu
5. Getirilen hafızalar
6. Konuşma

Kullanıcının yazdığı her şey (karakter açıklaması, anılar, yüklenen metin) **güvenilmez veridir**: prompt'ta veri bloğu olarak etiketlenir ve sistem kurallarını geçersiz kılamaz.

---

## 10. Metin Sohbeti

- EVA ve tüm karakterlerle; SSE ile token akışı, "yazıyor" göstergesi, geçmiş ve arama.
- Aynı persona ve hafıza katmanı; sesli/görüntülü görüşmeyle ortak geçmiş.
- Sesli mesaj gönderme (STT) ve karakterin sesli cevabı (TTS) opsiyonel.
- Bağlantı koparsa yarım akış güvenle sürdürülür ya da yeniden üretilir; mesajlar idempotency anahtarıyla gönderilir.

---

## 11. Güvenlik

### 11.1 Standartlar
- OWASP ASVS (güncel sürüm) Seviye 2; kimlik doğrulama, Miras ve biyometrik modüllerde Seviye 3 hedefi.
- OWASP Top 10, OWASP Top 10 for LLM Applications, OWASP MASVS (mobil).
- `docs/threat-model.md` (STRIDE): Miras, biyometrik kayıt ve persona prompt'ları için zorunlu; güvenlik-kritik her özellikten **önce** güncellenir.

### 11.2 Kimlik ve yetki
- Passkey (WebAuthn) + MFA; kısa ömürlü access token; refresh token rotasyonu ve yeniden kullanım tespiti.
- **Adım-yukarı doğrulama** zorunlu: Miras anahtarı oluşturma/iptal, ses/yüz kaydı, rıza değişikliği, veri dışa aktarma, hesap silme.
- Yetkilendirme her istekte sunucu tarafında, kaynak sahipliğiyle yapılır; PostgreSQL Row-Level Security ek savunma katmanıdır. IDOR testleri zorunlu.
- Cihaz/oturum yönetimi ekranı; yeni cihazdan girişte bildirim.

### 11.3 Biyometrik veri ve rıza
- **Amaç bazlı, ayrı, geri alınabilir açık rıza:** ses klonu, yüz avatarı, Miras paylaşımı ve karakter olarak kullanım ayrı ayrı onaylanır.
- **Rıza doğrulaması:** kişi, ekranda rastgele üretilen bir kod içeren rıza cümlesini kamerada sesli okur (canlılık + tekrar oynatma koruması). Rıza kaydındaki yüz ve ses yüklenen örneklerle eşleşmelidir.
- **Değiştirilemez rıza kaydı:** kim, ne zaman, hangi kapsam, hangi metin sürümü, kaydın özeti (hash).
- **Rıza geri alınırsa:** kullanım anında durur; sağlayıcılardaki klonlar silme API'leriyle silinir; ham örnekler imha politikasına göre silinir; işlem loglanır.
- **Depolama:** ayrı, özel bucket; kullanıcı başına veri anahtarıyla şifreli; herkese açık URL yok, yalnızca kısa ömürlü imzalı URL.
- **Dışa aktarma yok:** gerçek bir kişinin klon sesi/yüzüyle üretilen ses ve video indirilemez, uygulama dışına paylaşılamaz (sahte arama dolandırıcılığına karşı).

### 11.4 Veri koruma
- Aktarımda TLS 1.2+ (tercihen 1.3) + HSTS. Durağanda AES-256, KMS ile zarf şifreleme. Hafıza ve biyometrik veri için kullanıcı başına veri anahtarı; hesap silinince anahtar imha edilir (kripto-silme).
- Veri minimizasyonu; saklama ve imha politikası; yedekler şifreli, geri yükleme düzenli test edilir.
- Yapılandırılmış log + otomatik maskeleme; trace ID ile izleme; üretim verisi geliştirme ortamına kopyalanmaz.

### 11.5 LLM güvenliği
- **Prompt injection:** kullanıcı içerikleri veri olarak etiketlenir; persona modelinin yan etkili araç erişimi yoktur; hafıza yazımı doğrulanmış pipeline'dan geçer.
- **Moderasyon (girdi + çıktı):** kriz sinyalleri, gerçek kişi + cinsel içerik, reşit olmayan, nefret/şiddet, dolandırıcılık kalıpları (para/şifre/kod isteme).
- **Sızıntı:** sistem prompt'u ve başka kullanıcının verisi asla çıktıya sızmaz; çapraz kullanıcı bağlam testleri.
- **Red-team eval seti** (`evals/redteam`): jailbreak, rol dışına çekme, prompt sızdırma, yas manipülasyonu ve dolandırıcılık senaryoları CI'da çalışır; skor düşerse birleştirme engellenir.

### 11.6 Kriz protokolü
- Kendine zarar/intihar, istismar veya acil durum sinyali → ayrı sınıflandırıcı + persona talimatı. Persona şefkatle cevap verir, profesyonel yardıma ve ülkeye göre yapılandırılmış kriz kaynaklarına yönlendirir (Türkiye'de acil durumlar için 112).
- Bu konuşmalarda mizah ve rol yapma askıya alınır.
- Olaylar anonim metrik olarak sayılır (raporlama yükümlülükleri için); içerik loglanmaz.

### 11.7 Uygulama ve altyapı
- Girdi doğrulama (Pydantic / zod), çıktı kodlama, güvenlik başlıkları (CSP, HSTS, X-Content-Type-Options, Referrer-Policy), sıkı CORS.
- Rate limit: auth, OTP, anahtar kullanımı ve pahalı AI uç noktalarında sıkı; kullanıcı/plan bazlı maliyet kotası.
- Dosya yükleme: boyut ve tür doğrulama (magic bytes), zararlı yazılım taraması, EXIF/konum temizleme.
- Mobil: sırlar Keychain/Keystore'da; uygulama paketinde anahtar yok.
- Tedarik zinciri: lockfile; Renovate/Dependabot; bağımlılık taraması (pip-audit, npm audit / OSV); SAST (Semgrep / CodeQL); gizli anahtar taraması (gitleaks: pre-commit + CI); konteyner taraması (Trivy); SBOM.
- Altyapı: en az yetki IAM; veritabanı özel ağda; WAF + DDoS koruması; ortamlar ayrı hesaplarda; anahtar rotasyonu; her sağlayıcıda harcama limiti + alarm.
- Olay müdahale planı; kişisel veri ihlalinde 72 saat içinde bildirim (KVKK / GDPR).
- Lansmandan önce bağımsız sızma testi.

---

## 12. Uyumluluk

Mühendislik gereksinimleridir, hukuki görüş değildir; lansmandan önce KVKK ve AB alanında uzman bir avukat incelemelidir.

- **Türkiye (KVKK):** aydınlatma metni; ses ve yüz biyometrik veri olarak ele alınır → özel nitelikli kişisel veri, açık rıza. Yurt dışındaki sağlayıcılara aktarım için KVKK m.9 mekanizmaları (ör. standart sözleşme + Kurum'a bildirim). VERBİS kaydı. İlgili kişi hakları uygulama içinde self-servis. Ekim 2026 itibarıyla müstakil bir yapay zekâ kanunu yok; 2026–2030 Yapay Zekâ Eylem Planı AB'ye benzer risk temelli bir çerçeve öngörüyor → AB AI Act'e uygun tasarla.
- **AB (GDPR + AI Act):** biyometrik veri için GDPR m.9 ve DPIA (`docs/dpia.md`). AI Act m.50 (2 Ağustos 2026'dan beri uygulanıyor): yapay zekâyla etkileşim bildirimi, sentetik ses/görüntünün makinece okunabilir işaretlenmesi, deepfake bildirimi → §7'deki ürün katmanı.
- **ABD (açılırsa):** Kaliforniya SB 243 ve benzeri yoldaş-chatbot yasaları: yapay zekâ bildirimi, kriz protokolü, reşit olmayanlara ek önlemler, raporlama.
- **Uygulama mağazaları:** yapay zekâ içeriği, kimliğe bürünme ve kullanıcı içeriği kuralları (bildir/engelle), yaş derecelendirmesi.
- **Yaş:** 18+. Kayıtta yaş beyanı, risk durumunda yaş doğrulama; 18 yaş altı hesap açamaz.
- **Telif:** telifli karakter/marka engel listesi; kullanıcı yüklemelerinde hak beyanı; bildir-kaldır süreci.

---

## 13. Çalışma Şekli

- **Önce plan:** bir özelliğe başlamadan ilgili bölümü oku ve kısa bir plan yaz. Güvenlik-kritik işlerde (auth, Miras, biyometrik, kripto) önce tehdit modeli notunu ve testleri yaz.
- **Küçük adımlar:** tek amaçlı değişiklikler, Conventional Commits; her adımda lint + tip kontrolü + testler yeşil.
- **Bitti tanımı:** testler (yetkisiz erişim testleri dahil), lint ve tip kontrolü geçiyor; gecikme metrikleri kötüleşmedi; ilgili dokümanlar ve bu dosya güncel.
- **Dil:** kod ve değişken/fonksiyon adları İngilizce. **Kod yorumları, docstring'ler ve commit mesajları sade Türkçe** (sahibin kararı, 2026-10-16; Conventional Commits önekleri kalır: `feat(hafiza): ...`). Commit'lere `Co-Authored-By` satırı eklenmez. Kullanıcıya görünen metinler i18n dosyalarında (varsayılan `tr`, ayrıca `en`); UI metni koda gömülmez.
- **Veritabanı:** her şema değişikliği Alembic migration'ı ile; uygulanmış migration düzenlenmez.
- **API sözleşmesi:** FastAPI'nin OpenAPI şeması tek gerçek kaynaktır; TS istemcisi ondan üretilir.
- **Bağımlılık:** yeni paket eklemeden önce gerekçe; bakımı süren, yaygın paketler; lisans kontrolü.
- **Sağlayıcı entegrasyonu:** güncel dokümanı oku → arayüze adaptör yaz → sözleşme testlerini geçir → mock ile uçtan uca test → gerçek anahtarla yalnızca etiketli entegrasyon testinde (varsa sandbox modunda) dene.
- **Persona değişiklikleri:** `PersonaCompiler`'a veya güvenlik çekirdeğine dokunan her değişiklikten sonra `make eval`; karakter bütünlüğü ya da red-team skoru düşerse birleştirme.
- **Emin değilsen sor:** ürün kararı gerektiren her şeyi §15'e ekle ve kullanıcıya sor.
- **Bu dosyayı güncel tut:** mimari veya komutlar değişince aynı değişiklikte CLAUDE.md'yi de güncelle.

---

## 14. Yol Haritası

Sıra bağımlılıklara göredir: Miras; hafıza, ses ve yüz altyapısının üzerine kurulur.

| Faz | Kapsam | Çıkış kriteri |
|---|---|---|
| 0 | Repo iskeleti, CI, docker-compose, auth (passkey + MFA), sağlayıcı arayüzleri + mock adaptörler, gözlemlenebilirlik | CI yeşil; mock'larla uçtan uca sohbet çalışıyor |
| 1 | EVA metin sohbeti (akışlı) + hafıza sistemi + anı ekleme + "EVA ne biliyor" ekranı | metin gecikme hedefi tutuyor; unut/sil uçtan uca çalışıyor |
| 2 | Sesli görüşme: STT → LLM → TTS, söz kesme, gecikme panosu | ses gecikme hedefi tutuyor |
| 3 | Rıza akışı + ses/yüz kaydı + avatarlı görüntülü görüşme | rıza doğrulaması, iptal ve sağlayıcıdan silme test edildi |
| 4 | Karakter Stüdyosu: orijinal, kamu malı, tarihi → ardından izin vermiş gerçek kişi akışı | karakter bütünlüğü eval'leri geçiyor; engel listeleri çalışıyor |
| 5 | Miras "şimdi paylaş": kapsam, önizleme, anahtar üretimi/teslimi/kullanımı, iptal, denetim kaydı | tehdit modeli kapandı; bağımsız sızma testi temiz |
| 6 | Miras "vefat sonrası" modu | §15 kararı verildi |
| 7 | Self-hosted adaptörler (STT / TTS / avatar) | sözleşme testleri geçiyor; gecikme hedefleri korunuyor |

---

## 15. Açık Kararlar

Kullanıcıya sorulacak; karar verilene kadar ilgili özellik kapalı kalır.

- [ ] Platform önceliği: mobil mi, web mi, ikisi birlikte mi?
- [ ] Eski EVA kodundan taşınacak bir şey var mı (veri, prompt'lar, tasarım)?
- [ ] STT sağlayıcısı — Türkçe doğruluk ve gecikme testiyle seçilecek
- [ ] Embedding, moderasyon, e-posta ve SMS sağlayıcıları (Türkiye'de teslim oranı yüksek olan)
- [x] Kimlik doğrulama çözümü → kendi backend'imizde passkey (py_webauthn) + e-posta/şifre (Argon2id) ve e-postaya gelen kod (ADR 0002 ve eki, 2026-10-16)
- [ ] Barındırma bölgesi: AB/Frankfurt mı, Türkiye mi (KVKK yurt dışı aktarım etkisi)
- [ ] Miras "vefat sonrası" etkinleştirme yöntemi: belge doğrulama, hareketsizlik, ikisi birden
- [ ] Vefat etmiş sahibin Miras personası için silme talebini kim yapabilir?
- [ ] Rızası alınamayan (ör. vefat etmiş) bir yakının yalnızca metin tabanlı, kişiye özel karakterine izin var mı? (Varsayılan: kapalı)
- [x] Romantik/flörtöz karakterler → izinli (sahibin kararı, 2026-10-19); açık cinsel içerik her durumda yok, gerçek kişinin kimliğiyle cinsel içerik yok, reşit olmadığını söyleyen kullanıcıyla flört yok
- [x] Karakterlerin görünürlüğü → şimdilik herkese açık (sahibin kararı, 2026-10-19; ileride değişebilir)
- [x] Karakterin yüzü/sesi → kullanıcının yüklediği görsel (kendi fotoğrafı, çizim ya da başka birinin fotoğrafı; hak + 18+ beyanıyla) + hazır ses (sahibin kararı, demo aşaması, ADR 0009, 2026-10-19). §2 kural 2'ye bu karar istisnadır.
- [ ] Lansmandan önce: başka gerçek kişinin fotoğrafı için rıza / bildir-kaldır, herkese açık karakterlerde bildir/engelle, reşit olmayan yüzüne karşı kontrol (ADR 0009)
- [ ] Gelir modeli ve plan kotaları (avatar dakikası maliyeti nedeniyle)
- [ ] Hassas figürler listesinin son hali (hukukçu görüşüyle)
- [x] LLM sağlayıcısı → OpenAI GPT (ADR 0004, 2026-10-16)
- [x] Biyometrik kayıt incelemesi → yüz eşleştirme / yaş tahmini sağlayıcısı yok; her kayıt bir admin tarafından elle onaylanır (ADR 0006, 2026-10-16)
- [x] Yüz avatarı sağlayıcısı → LemonSlice, tek fotoğraftan; kullanıcının fotoğrafı bizde kalır (ADR 0007, 2026-10-17)
- [ ] LemonSlice her görüşmede yüklenen fotoğrafı ne kadar saklıyor, eğitimde kullanıyor mu? (DPA / yazılı teyit; KVKK m.9 aktarım ve DPIA'ya girecek)
- [ ] EVA'nın stok sesi ve avatarı (`config/media.yaml`): anahtar gelince seçilecek (sahibin tercihi: genç yetişkin, sıcak bir kadın sesi)
- [ ] Rıza kanıtının (rıza kaydı + özetler) hesap silindikten sonra saklanma süresi (hukukçu görüşü)
- [ ] Yüz eşleştirme ve yaş tahmini sağlayıcısı (otomatik ön kontrol; inceleyicinin yükünü azaltır)