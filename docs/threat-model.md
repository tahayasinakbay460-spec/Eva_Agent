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
