# ADR 0010: Miras — "şimdi paylaş"

Tarih: 2026-10-19 · Durum: kabul edildi (sahibin 2026-10-19 kararları)

## Bağlam

Miras (CLAUDE.md §8): sahibin dijital kişiliği (kişilik + seçtiği anılar + klon sesi + yüzü) bir
güvenlik anahtarıyla yakınına verilir. Faz 5 yalnızca "şimdi paylaş" modunu kapsar; "vefat sonrası"
Faz 6. Sahibin kararları: anahtar 30 gün geçerli; en fazla 5 alıcı; **ses ve yüz zorunlu**
(onaylı klon sesi ve yüz fotoğrafı olmayan kullanıcı Miras gönderemez; Miras'ın özü görüntülü
görüşme); Miras rızası yeni video çekmeden, adım-yukarı doğrulama + açık onay metniyle verilir.

## Karar

- **Persona:** sahibin tek bir `type="legacy"` personası. Alıcıya giden şey onun dondurulmuş bir
  **sürümü**dür (`persona_versions`: tanım + kapsamdaki anılar `canon_memories` olarak, salt-okunur).
  Sahip personayı değiştirip yeni sürüm yayınlayabilir; mevcut alıcılar yeni sürüme geçer.
- **Kişilik taslağı:** işçi (`llm.background`), sahibin kapsamdaki anılarından ve kendi mesajlarından
  bir `PersonaDefinition` taslağı yazar; sahip okur, düzeltir, kaydeder. Sıcak yolda değil.
- **Kapsam:** `memories.legacy_scope` ve `sensitivity`; hassas anılar varsayılan hariç.
- **Anahtar:** 20 bayt CSPRNG (160 bit) → Crockford Base32, 4'lü gruplar + kontrol karakteri:
  `EVA-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-C`. Girişte boşluk, tire, küçük harf ve I/L/O
  karışıklıkları normalize edilir. Saklanan: `HMAC-SHA-256(pepper, normalize(key))`. Biber
  (`EVA_LEGACY_KEY_PEPPER`) dev'de `backend/.dev_legacy_pepper` dosyasından (git'e girmez),
  staging/prod'da secret manager'dan gelir; yoksa uygulama açılmaz.
- **Grant (`legacy_grants`):** sahip, persona, alıcı e-postası (normalize), anahtar özeti, durum
  (`pending` | `redeemed` | `revoked` | `expired`), `expires_at` (30 gün), oluşturma/kullanma
  zamanları, kullanan hesap. Sahip başına en fazla 5 açık (pending + redeemed) grant.
- **Kullanma:** alıcı kendi EVA hesabıyla girer → `POST /legacy/redeem` (anahtar) → geçerliyse
  anahtarın gönderildiği e-postaya 6 haneli kod (mevcut kod akışı altyapısı) → `POST
  /legacy/redeem/verify` → `legacy_access` satırı açılır, grant `redeemed`. Sahip kendi anahtarını
  kullanamaz. Bütün hatalar aynı: `invalid_or_expired`. Hesap başına art arda 5 hatada 24 saat kilit.
- **Erişim:** Miras personası yalnızca sahibine ve aktif `legacy_access` sahibi alıcılara görünür.
  Sohbet ve görüşme her turda erişimi ve sahibin ses/yüz rızasını kontrol eder.
- **Ses ve yüz:** Miras görüşmesinde ses ve yüz her zaman sahibinin aktif klonu/fotoğrafıdır
  (alıcı değiştiremez). Sahip rızasını geri alırsa ya da Miras rızasını çekerse erişim durur.
- **Alıcı hafızası:** alıcının konuşmalarından çıkan anılar alıcı + Miras personası kapsamındadır;
  temel personayı değiştirmez. Alıcı kendi anılarını ekleyebilir (`source=recipient_added`).
- **E-posta:** sabit şablon; persona içeriği yok; yalnızca anahtar, sahibin görünen adı ve kendi
  alan adımıza bağlantı. Sağlayıcı seçilene kadar `dev_mailbox`.
- **Denetim:** `legacy.created`, `legacy.sent`, `legacy.redeem_failed`, `legacy.redeemed`,
  `legacy.revoked`; sahibe kullanım bildirimi.

## Sırayla yapılacaklar

1. Tehdit modeli (§6) ✔ · 2. veri modeli + anahtar modülü ✔ · 3. kişilik taslağı ✔ · 4. kapsam ✔ ·
5. önizleme + yayın ✔ · 6. anahtar üretimi/teslimi · 7. kullanma (iki faktör) · 8. alıcı deneyimi (yazışma +
sesli/görüntülü) · 9. iptal + bildirim · 10. Miras eval'leri · 11. web arayüzü.

## Uygulama notları (adım 2–5)

- Önizleme: sahip Miras personasıyla canlı taslak + şu an dahil anılar (kanon) ile konuşur;
  taslak yoksa `legacy_draft_missing`. Ses/yüz her zaman sahibinin (`media_owner_id`).
- Yayın: `POST /legacy/persona/publish` (adım-yukarı) taslak + onaylı ses + yüz ister; tanımı ve
  kanon anıları `persona_versions`'a dondurur (sürüm 1, 2, ...). Sonraki düzenlemeler yeni yayına kadar
  alıcıya gitmez.
- Kapsam: `PATCH /memories/{id}` `legacy_scope` (`included` | `excluded`); sahibin açık seçimi
  hassasiyet varsayılanını ezer.

## Sonuçlar

- Yeni tablolar: `persona_versions`, `legacy_grants`, `legacy_access`; `consents.purpose` için
  `legacy_share`.
- Bağımsız sızma testi Faz 5 çıkış kriteridir ve dış bir firmayla lansmandan önce yapılır.
