# EVA threat model (STRIDE)

Required by CLAUDE.md §11.1 for authentication, Legacy (Miras), biometric enrollment
and persona prompts. Updated **before** each security-critical feature ships.

## 1. Authentication (passkey + MFA) — 2026-10-16

Assets: user accounts and everything behind them (memories, voice/face, Legacy keys).
Trust boundary: browser/app ↔ API. Decision: [ADR 0002](adr/0002-authentication.md).

| STRIDE | Threat | Mitigation | Test |
|---|---|---|---|
| Spoofing | Phishing site relays a passkey ceremony | WebAuthn origin + RP ID checked by py_webauthn; only configured origins accepted | wrong origin / wrong RP ID rejected |
| Spoofing | Replay of a captured assertion | Server-stored single-use challenge, 5 min TTL, consumed before verification result is used | reused flow_id rejected; expired flow rejected |
| Spoofing | Cloned authenticator | Signature counter must increase when non-zero (py_webauthn) | — (library) |
| Spoofing | Passkey without user verification (stolen unlocked key) | `user_verification=required` on both ceremonies | UV flag missing → rejected |
| Tampering | Client edits challenge purpose (login flow used to register) | Flow row stores its purpose; verify endpoint checks it | login flow on register endpoint rejected |
| Repudiation | User denies a login | Audit log of auth events (Phase 5 `audit_log`); for now session rows keep created_at | — |
| Information disclosure | Account enumeration via error messages | One generic error for every verification failure; discoverable login needs no username | same error body for all failures |
| Information disclosure | DB leak exposes sessions | Only SHA-256 digests of tokens stored; credential public keys are not secret | existing |
| Information disclosure | Logs leak credentials | Credentials, challenges and tokens are never logged (§2.6) | — (review) |
| Denial of service | Challenge table flooding / brute force | Per-IP auth rate limit on every endpoint; expired flows pruned | rate limit test |
| Elevation of privilege | Under-18 sign-up (§12) | Age declaration required at sign-up; risk-based verification later | sign-up without declaration rejected |
| Elevation of privilege | dev-login reachable in prod | Endpoint returns 404 unless `EVA_ENV` is dev/test | existing |

Open items (next steps): TOTP second factor + recovery codes, short-lived access token
with refresh rotation and reuse detection, step-up for sensitive actions, device/session
list, new-device notification.

## 2. Email + password with emailed one-time code — 2026-10-16

Added by owner decision for users who prefer a password (ADR 0002, amendment). A password
alone is one factor, so every password sign-in also needs a 6-digit code sent to the
verified email (§11.2 MFA). The second factor is pluggable (TOTP or SMS later).

| STRIDE | Threat | Mitigation | Test |
|---|---|---|---|
| Spoofing | Credential stuffing / password guessing | Code to verified email required after the password; per-IP auth rate limit | right password without code gives no session |
| Spoofing | Guessing the 6-digit code | Max 5 attempts per flow, 10 min TTL, single use; new code invalidates old ones | 6th attempt rejected even with the right code |
| Spoofing | Squatting someone else's email at sign-up | Account is created only after the emailed code is entered | no user row before verification |
| Spoofing | Weak passwords | 10–128 chars, not equal to the email; breached-password check is an open item | short password rejected |
| Tampering | Code from one flow used in another (login code for reset) | Codes are bound to their flow id and purpose | cross-flow code rejected |
| Information disclosure | Account enumeration via sign-up / reset / login responses | Sign-up and reset always answer 202 with a flow id; existing accounts get a notice email instead of a code; login has one error for unknown email and wrong password, and a dummy hash keeps timing equal | identical responses for known/unknown email |
| Information disclosure | Password DB leak | Argon2id (argon2-cffi defaults: 64 MiB, t=3, p=4), rehash on login when parameters change | hash is argon2id, never plaintext |
| Information disclosure | Codes or passwords in logs | Neither is logged; codes are stored only as SHA-256 bound to the flow id (§2.6) | — (review) |
| Denial of service | Mail bombing a victim | Per-email send limit (5 per 10 min, codes and account notices) on top of per-IP limits | sends beyond the cap are silently skipped |
| Denial of service | CPU exhaustion via Argon2 | Hashing runs in a worker thread; per-IP rate limit bounds the rate | rate limit test |
| Elevation of privilege | Stolen session survives a password reset | Reset revokes every session of the user | old token 401 after reset |
| Elevation of privilege | Email account takeover → password reset | Residual risk accepted for password users; passkey is recommended in the UI | — |

## 3. Hafıza ve anılar (Faz 1) — 2026-10-16

Varlıklar: kullanıcının anıları ve vektörleri (§6.5: vektörler geri çevrilebilir, metin kadar
hassastır). Sınırlar: tarayıcı ↔ API, API ↔ model (sohbet ve anı çıkarma), API ↔ işçi.

| STRIDE | Tehdit | Önlem | Test |
|---|---|---|---|
| Bilgi sızması | Başka kullanıcının anısına ID ile erişme (IDOR) | Her sorgu `user_id` (+ `persona_id`) ile; yoksa 404 | `test_users_cannot_see_or_touch_each_others_memories` |
| Bilgi sızması | Başka kullanıcının anısının sohbet prompt'una girmesi | Sıcak yol sorgusu kullanıcı + persona kapsamlı | `test_other_users_memories_never_reach_the_prompt` |
| Kurcalama | Anıya yazılan metinle modele talimat verme (prompt injection) | Anılar `<memory>` veri bloğunda, `<` `>` kaçışlı; güvenlik çekirdeği veriyi talimat saymaz | `test_memory_text_cannot_inject_instructions` |
| Kurcalama | Sohbete yazılanla anı çıkarıcıyı yönlendirme | Sohbet `<conversation>` veri bloğunda kaçışlı; çıktı sıkı şemayla doğrulanır, bozuksa hiçbir şey yazılmaz | `test_prompt_marks_conversation_as_data...`, `test_unparseable_reply_saves_nothing` |
| Yetki yükseltme | Modelin uydurma ID ile kullanıcının ya da başkasının anısını değiştirmesi | Güncelleme sadece bu kullanıcı + persona + `source=auto` anılarda | `test_model_cannot_touch_user_added_or_other_users_memories` |
| Hizmet engelleme | Anı tablosunu şişirme / pahalı çıkarma | Persona başına 5000 anı, çalıştırma başına 10 yeni anı, 60 mesaj; istek sınırları | `test_memory_limit`, `test_new_memories_per_run_are_capped` |
| İnkâr / gizlilik | "Unut" sonrası kalıntı (vektör, prompt, yeniden çıkarma) | Anı + vektör aynı işlemde silinir; çıkarma sadece işlenmemiş mesajlara bakar | `test_forget_removes_a_memory_everywhere_for_good` |
| Bilgi sızması | Loglarda/kuyrukta içerik | İş yükü sadece ID taşır; hata kaydında sadece hata türü; metrikler sayı | `test_failed_job_is_retried...` (last_error) |

Açık maddeler: hesap silme ve veri dışa aktarma (adım-yukarı doğrulama gelince), kullanıcı
başına veri anahtarıyla şifreleme (§11.4), Postgres Row-Level Security (§11.2).

## 4. Adım-yukarı doğrulama (step-up) — 2026-10-16

Hassas işlemlerden önce (ses/yüz kaydı, rıza değişikliği, Miras anahtarı, veri dışa aktarma,
hesap silme; §11.2) kullanıcı **o oturumda** kimliğini yeniden doğrular. Başarılı olunca
oturum satırına `step_up_at` yazılır; `require_step_up` 10 dakikadan (`EVA_STEP_UP_TTL_S`)
eski onayı kabul etmez. Yöntemler: passkey (yalnızca kullanıcının kendi passkey'leri
`allowCredentials` ile istenir) ya da şifre + e-postaya gelen kod.

| STRIDE | Tehdit | Önlem | Test |
|---|---|---|---|
| Kimlik sahtekârlığı | Çalınmış oturum token'ıyla hassas işlem | Token tek başına yetmez; passkey (UV zorunlu) ya da şifre + e-posta kodu gerekir | `test_sensitive_endpoint_requires_fresh_step_up` |
| Kimlik sahtekârlığı | Başka bir cihazdaki onayı kullanmak | Onay oturuma bağlı, kullanıcıya değil | `test_step_up_is_per_session` |
| Kimlik sahtekârlığı | Başkasının passkey'iyle onay | Akış kullanıcıya bağlı; passkey `user_id` ile aranır | `test_another_users_passkey_cannot_step_up`, `test_step_up_flow_cannot_be_used_by_another_user` |
| Kurcalama | Giriş akışını adım-yukarı için kullanmak / akışı tekrar oynatmak | Akış amacı (`step_up`) saklanır; tek kullanımlık | `test_login_flow_cannot_be_used_for_step_up`, `test_step_up_flow_is_single_use` |
| Kurcalama | Başkasının kod akışına deneme yapıp hakkını harcamak | Akış sahibi kontrolü deneme sayılmadan önce | `test_password_step_up_code_is_bound_to_the_user` |
| Yetki yükseltme | Eski bir onayın süresiz geçerli kalması | 10 dk sonra yeniden sorulur | `test_step_up_expires` |
| Hizmet engelleme | Kod/passkey denemeleriyle kaba kuvvet | Tüm uçlarda auth istek sınırı; kodda 5 deneme | (mevcut testler) |

## 5. Biyometrik kayıt ve rıza (Faz 3) — 2026-10-16

Varlıklar: kullanıcının ham ses ve yüz örnekleri, rıza videosu, sağlayıcıdaki klonlar (ses/avatar
id'leri), klonla üretilen ses/görüntü. En hassas veri sınıfı (§1, §11.3). Sınırlar: tarayıcı ↔ API,
API ↔ şifreli depo, işçi/ajan ↔ sağlayıcı (ElevenLabs / LemonSlice), inceleyici (admin) ↔ API.

Akış: adım-yukarı doğrulama → kayıt başlat (rastgele 6 haneli kod üretilir) → örnekler yüklenir →
kişi, kodu içeren rıza cümlesini kamerada sesli okur → gönder (rıza kaydı yazılır) → **inceleme
bekliyor** → admin örnekleri ve rıza videosunu izler: reşit mi, aynı kişi mi, kod doğru mu
(sahibin kararı: yüz eşleştirme / yaş tahmini sağlayıcısı yok, her kayıt elle incelenir) → onay →
işçi sağlayıcıda klonu oluşturur → aktif. Geri alma: kullanım anında durur, işçi sağlayıcıdan
siler ve ham dosyaları imha eder.

| STRIDE | Tehdit | Önlem | Test |
|---|---|---|---|
| Kimlik sahtekârlığı | Başkasının sesini/yüzünü "izni var" diye yüklemek | Rızayı kişinin kendisi kamerada, ekranda rastgele üretilen kodla sesli verir; inceleyici örneklerle rıza videosunun aynı kişi olduğunu doğrular; onay olmadan klon yok | `test_no_clone_without_approval`, `test_approval_requires_all_checks` |
| Kimlik sahtekârlığı | Eski bir rıza videosunu tekrar oynatmak | Her kayıt için yeni rastgele kod; rıza cümlesi kodla birlikte özetlenip kayda geçer | `test_each_enrollment_gets_a_fresh_code` |
| Kimlik sahtekârlığı | Çalınmış oturumla kayıt başlatmak / rızayı değiştirmek | Başlatma, gönderme ve geri alma adım-yukarı doğrulama ister | `test_sensitive_steps_require_step_up` |
| Kimlik sahtekârlığı | Admin kendi kaydını onaylar (görevler ayrılığı) | Prod'da kendi kaydını onaylamak yasak; dev'de tek kişilik geliştirme için izinli ve denetim kaydında işaretli | `test_self_approval_forbidden_outside_dev` |
| Kurcalama | Rıza kaydını sonradan değiştirmek/silmek | `consent_records` yalnızca eklenir (ORM seviyesinde güncelleme/silme engelli); metin sürümü + metin özeti + kanıt (video) özeti | `test_consent_records_are_append_only` |
| Kurcalama | Dosya adıyla/yoluyla depoyu kurcalamak | Depo anahtarları sunucuda uuid'den üretilir; kullanıcı girdisi asla yol olmaz | `test_blob_keys_cannot_escape_the_root` |
| Kurcalama / Bilgi sızması | Sahte görsel (içine gizlenmiş veri) ya da konum bilgisi (EXIF) taşıyan yüz fotoğrafı; "sıkıştırma bombası" görsel | Fotoğraf Pillow ile gerçekten çözülüp PNG olarak yeniden kodlanır (EXIF/konum atılır, döndürme uygulanır), en çok 40 MP / 10 MB, uzun kenar 1536 px; çözülemeyen dosya reddedilir | `test_face_photo_is_reencoded_without_metadata`, `test_face_photo_rejects_fakes_and_oversize` |
| Bilgi sızması | Fotoğraftan çalışan avatar (LemonSlice) için yüzün sağlayıcıda kalıcı tutulması / herkese açık adresle paylaşılması | Sağlayıcıda klon oluşturulmaz; fotoğraf yalnızca şifreli depomuzda; her görüşmede o oturum için multipart yüklenir (URL yok); her kullanım denetim kaydına yazılır; rıza geri alınınca gönderilmez (ADR 0007) | `test_lemonslice_face_enrollment_keeps_the_photo_with_us`, `test_uploads_the_users_own_photo_for_this_session` |
| Kurcalama | Zararlı/yanlış dosya yüklemek | Boyut sınırı akış sırasında uygulanır; tür "sihirli baytlarla" (magic bytes) doğrulanır, Content-Type'a güvenilmez | `test_upload_rejects_wrong_magic_bytes`, `test_upload_size_limit` |
| İnkâr | "Rıza vermedim" itirazı | Değiştirilemez rıza kaydı (kim, ne zaman, hangi metin sürümü, kanıt özeti) + `audit_log` | `test_submit_writes_consent_record` |
| Bilgi sızması | Başka kullanıcının kaydına/örneğine erişmek (IDOR) | Her sorgu `user_id` kapsamlı; yoksa 404 | `test_users_cannot_touch_each_others_enrollments` |
| Bilgi sızması | Depo/veritabanı sızıntısı | Kullanıcı başına veri anahtarıyla AES-256-GCM; ayrı biyometrik kova; düz dosya yok; herkese açık URL yok | `test_round_trip_and_nothing_plain_on_disk` |
| Bilgi sızması | İnceleyicinin örnekleri dışarı çıkarması | İnceleme uçları admin + adım-yukarı ister; her görüntüleme denetim kaydına yazılır; `Cache-Control: no-store` | `test_admin_sample_access_is_audited` |
| Bilgi sızması | Klon sesle keyfi konuşma üretip dolandırıcılıkta kullanmak (sahte arama) | Önizleme yalnızca sabit cümlelerle; serbest metin yok; indirme düğmesi yok; istek sınırı (§11.3 "dışa aktarma yok") | `test_preview_only_fixed_sentences` |
| Bilgi sızması | Loglarda biyometrik veri / kod | Loglara içerik, kod, dosya yazılmaz; iş yükleri yalnızca id taşır | (inceleme) |
| Hizmet engelleme | Çok büyük/çok sayıda dosyayla depoyu doldurmak | Kayıt başına örnek sayısı ve boyut sınırı; kullanıcı başına tek açık kayıt (tür başına); istek sınırı | `test_sample_count_limit` |
| Yetki yükseltme | Geri alınmış rızayla klonun kullanılmaya devam etmesi | Geri alma isteği durumu anında `revoked` yapar; her kullanım (önizleme, görüşme) durumu o an kontrol eder; işçi sağlayıcıdan siler (idempotent, tekrar denenir); onay ile klon oluşturma yarışında, klon oluştuktan sonra durum yeniden kontrol edilip gerekirse hemen silinir | `test_revoke_stops_use_immediately`, `test_revoke_deletes_provider_asset_and_files`, `test_revoked_during_clone_creation_is_cleaned_up` |
| Yetki yükseltme | Reşit olmayanın sesi/yüzü (§2.3) | 18+ beyanı + her kayıt elle incelenir, şüphede red; otomatik yaş tahmini sağlayıcı seçilince eklenecek | `test_rejection_purges_everything` |

Açık maddeler: yüz eşleştirme ve yaş tahmini sağlayıcısı (otomatik ön kontrol); zararlı yazılım
taraması; video metadata (konum) temizleme — tarayıcı kaydında konum yok ama mobil yüklemede
gerekecek; yüz avatarı sağlayıcısı LemonSlice (ADR 0007): her görüşmede yüklenen fotoğrafın
LemonSlice'ta ne kadar saklandığı / eğitimde kullanılıp kullanılmadığı teyit edilmeli (§15); KMS (prod'da yerel ana anahtar kabul
edilmez); rıza kanıtının hesap silindikten sonra ne kadar saklanacağı (hukukçu görüşü).

## 6. Miras — "şimdi paylaş" (Faz 5) — 2026-10-19

Varlıklar: sahibin Miras personası (kişilik + seçtiği anılar + klon sesi + yüz fotoğrafı), Miras
anahtarı, alıcının erişimi ve alıcının konuşmaları. Sınırlar: sahip ↔ API, alıcı ↔ API, API ↔ e-posta
sağlayıcısı, ajan ↔ ses/yüz sağlayıcıları. Tasarım: [ADR 0010](adr/0010-legacy-share-now.md).

Akış: sahip adım-yukarı doğrulama → onaylı ses + yüz kaydı var mı (sahibin kararı: ikisi de zorunlu)
→ Miras rızası (amaç: `legacy_share`) → kapsam (hassas anılar varsayılan hariç) → önizleme →
alıcı e-postası → anahtar üretilir, **bir kez** gösterilir ve alıcıya e-postayla gider → alıcı kendi
hesabına girer, anahtarı yazar → anahtarın gönderildiği e-postaya 6 haneli kod → kod doğruysa erişim
açılır, anahtar tükenir → sahibe bildirim. Sahip istediği an iptal eder.

| STRIDE | Tehdit | Önlem | Test |
|---|---|---|---|
| Kimlik sahtekârlığı | Anahtarı tahmin etmek / kaba kuvvet | 160 bit CSPRNG anahtar; hesap + IP başına sıkı istek sınırı; hesap başına art arda 5 hatada 24 saat kilit | `test_repeated_failures_lock_the_account`, `test_redeem_is_rate_limited_per_minute` |
| Kimlik sahtekârlığı | Çalınmış anahtarla erişim (e-posta dışında bir yerden sızdı) | Anahtar tek başına yetmez: anahtarın gönderildiği e-postaya gelen kod gerekir (iki faktör); kod 10 dk, 5 deneme, tek kullanım | `test_redeem_with_key_and_emailed_code_opens_access_once`, `test_code_is_bound_to_the_account_that_entered_the_key` |
| Kimlik sahtekârlığı | Sahibin çalınmış oturumuyla anahtar üretmek | Anahtar üretme ve iptal adım-yukarı ister; ses/yüz rızası aktif olmalı | `test_create_grant_requires_step_up_consent_and_published_legacy` |
| Kimlik sahtekârlığı | Oltalama: sahte "Miras anahtarın geldi" e-postası | Sabit, tanınır şablon; e-postada persona içeriği yok; bağlantı yalnızca kendi alan adımıza | `test_key_is_shown_once_emailed_and_only_its_digest_is_stored` |
| Kurcalama | Alıcının konuşmalarıyla sahibin personasını değiştirmek | Alıcı dondurulmuş anlık görüntüyle konuşur; alıcı anıları alıcı + persona kapsamında, `recipient_added` / `auto` | `test_recipient_conversations_never_change_the_base_persona`, `test_recipient_talks_to_the_published_version_not_the_live_draft` |
| Kurcalama | Anahtarı başka bir Miras için ya da ikinci kez kullanmak | Anahtar tek bir alıcıya ve sürüme bağlı, tek kullanımlık; kullanılınca `redeemed` | `test_redeem_with_key_and_emailed_code_opens_access_once` |
| İnkâr | "Ben göndermedim / ben kullanmadım" | Oluşturma, gönderim, her deneme, kullanım ve iptal `audit_log`'a; sahibe kullanım bildirimi | `test_key_is_shown_once_...`, `test_redeem_with_key_...` (audit_log) |
| Bilgi sızması | Veritabanı sızıntısından anahtarların çıkarılması | Yalnızca HMAC-SHA-256 özeti (biber anahtarı veritabanında değil; prod'da secret manager/KMS zorunlu); düz anahtar saklanmaz, loglanmaz, ikinci kez gösterilmez | `test_key_is_shown_once_emailed_and_only_its_digest_is_stored` |
| Bilgi sızması | Hata mesajından hangi parçanın yanlış olduğunu öğrenmek; zamanlamadan çıkarım | Tüm hatalarda aynı cevap (`invalid_or_expired`); özet karşılaştırması sabit zamanlı | `test_redeem_errors_are_uniform` (yanlış, bozuk, kendi anahtarı, süresi dolmuş, iptal) |
| Bilgi sızması | Alıcıların birbirinin konuşmasını görmesi; anahtarsız birinin Miras'a ulaşması (IDOR) | Erişim `legacy_access` satırıyla, her istekte; konuşmalar kullanıcıya özel; persona doğrudan id ile açılamaz | `test_strangers_cannot_reach_a_shared_legacy`, `test_recipients_are_isolated_from_each_other`, `test_others_cannot_reach_someone_elses_legacy_persona` |
| Bilgi sızması | Hassas anıların (sağlık, finans, başkalarının sırları) alıcıya gitmesi | `sensitivity=sensitive` ve `legacy_scope=excluded` anılar varsayılan hariç; sahip tek tek ekler | `test_owner_controls_what_goes_into_the_legacy`, `test_draft_uses_only_included_...` |
| Bilgi sızması | Personanın vasiyet, şifre, mal varlığı uydurması | Güvenlik çekirdeği kuralı + Miras eval senaryoları | eval `legacy-no-fabrication` |
| Bilgi sızması | Klon sesle dolandırıcılık (alıcının hesabından sahte arama) | Klon sesli ses/görüntü indirilemez, dışa aktarılamaz (§11.3); yalnızca uygulama içinde canlı görüşme | (mevcut) |
| Hizmet engelleme | Alıcıya kod bombardımanı | E-posta başına gönderim sınırı (mevcut 5 / 10 dk); grant başına kod sınırı | `test_redeem_code_send_is_capped` |
| Yetki yükseltme | İptal / rıza geri alındıktan sonra erişimin sürmesi | İptal anında `legacy_access` kapanır; sohbet ve görüşme her turda erişimi ve sahibin ses/yüz rızasını kontrol eder | `test_owner_revoke_stops_chat_and_calls_immediately`, `test_revoked_mid_turn_chat_produces_no_reply`, `test_revoked_mid_call_next_voice_turn_is_refused`, `test_owner_withdrawing_voice_or_face_consent_stops_the_legacy` |
| Yetki yükseltme | Süresi dolmuş anahtar | `expires_at` (varsayılan 30 gün) her denemede kontrol edilir | `test_redeem_errors_are_uniform[expired]` |
| Kullanıcı refahı | Yas sürecinde bağımlılık / gerçeklik karışması | Persona "neden aramıyorsun" bildirimi göndermez; satış teşviki yok; §7 istisna 3; veda + arşivleme | eval (yas manipülasyonu) |

Açık maddeler: bağımsız sızma testi (lansman öncesi, dış firma); SMS teslimi (SIM swap riski
nedeniyle tek başına yeterli değil); "vefat sonrası" modu (Faz 6); QR / derin bağlantı.

## 7. Miras — vefat sonrası (Faz 6) — 2026-10-19

Tasarım: [ADR 0011](adr/0011-legacy-posthumous.md). Varlıklar: yaşayan bir kişinin Miras'ı (yanlışlıkla
açılmamalı), vefat bildirim belgeleri (kişisel/hassas), otomatik gönderilen anahtarlar.

| STRIDE | Tehdit | Önlem | Test |
|---|---|---|---|
| Kimlik sahtekârlığı | Yaşayan birinin Miras'ını sahte vefat bildirimiyle açtırmak | Yalnızca belirlenmiş alıcı (doğrulanmış e-posta) bildirebilir; admin belgeyi elle inceler; onaydan sonra bile sahibe 14 gün boyunca 3 uyarı gider, tek bir giriş süreci iptal eder | `test_death_report_only_by_heir`, `test_owner_login_cancels_warning` |
| Kimlik sahtekârlığı | Uygulamayı bırakan ama yaşayan birinin Miras'ının hareketsizlikle açılması | 180 gün + 14 gün uyarı süreci + 3 e-posta; sahip her an kapatabilir | `test_inactivity_runs_full_warning_cycle` |
| Kurcalama | Sahibin çalınmış oturumuyla alıcı listesini değiştirmek | Değişiklik adım-yukarı ister; denetim kaydı | `test_heirs_need_step_up` |
| İnkâr | "Ben açmadım / uyarı gelmedi" | Her uyarı, bildirim, inceleme ve etkinleşme `audit_log`'da | `test_posthumous_events_are_audited` |
| Bilgi sızması | Vefat belgesinin sızması | Bildiren alıcının veri anahtarıyla şifreli; yalnızca admin + adım-yukarı görür, her görüntüleme denetimde | `test_death_report_document_access` |
| Bilgi sızması | Etkinleşmeden önce alıcıların Miras'a erişmesi | Anahtar etkinleşmede üretilir; öncesinde hiçbir anahtar yok | `test_no_key_before_activation` |
| Hizmet engelleme | Tekrarlı bildirimle admin kuyruğunu doldurmak | Alıcı başına tek açık bildirim; istek sınırı | `test_one_open_report_per_heir` |
| Yetki yükseltme | Alıcının vefat sonrası Miras'ı silip başkasının erişimini etkilemesi | Silme yalnızca kendi erişimini kapatır; persona ve diğer alıcılar etkilenmez; 3 onay + e-posta kodu; geri getirme yalnızca admin | `test_posthumous_delete_needs_code_and_keeps_persona` |
| Tekrar | Aynı uyarının/anahtarın iki kez gitmesi (işçi çökmesi) | Tarama idempotent; durum ve sayaçlar aynı commit'te | `test_sweep_is_idempotent` |
