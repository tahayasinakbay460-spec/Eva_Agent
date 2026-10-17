# ADR 0007: Yüz avatarı sağlayıcısı LemonSlice — tek fotoğraftan, yüz bizde kalır

Tarih: 2026-10-17 · Durum: kabul edildi (sahibin 2026-10-16/17 kararı)

## Bağlam

Görüntülü görüşmede kullanıcının (ve EVA'nın) konuşan yüzü için LITE/yalnızca-yüz çalışan bir
sağlayıcı gerekiyor (CLAUDE.md §4.2: STT/LLM/TTS bizde). Denenenler:

- **HeyGen LiveAvatar:** özel avatar için resmî API yok (yalnızca panel), avatar başına ücretli
  slot (1 avatar ≈ 99 $/ay), silme "yumuşak silme". Her kullanıcı için avatar = ölçeklenmez.
- **Anam:** çalıştı (sahibin kendi yüzüyle ilk gerçek görüntülü görüşme, 6. oturum) ama plan
  başına aynı anda görüşme sınırı sert; fazlası reddediliyor. Yatırımcı demosu için yetersiz.
- **LemonSlice:** "zero-shot": her oturumda tek bir fotoğraf (ya da önceden oluşturulmuş avatar
  id'si) alır, eğitim/klon yok. Bizim LiveKit odamıza katılır, sesi odanın standart avatar
  kanalından alır. Aynı anda sınırı aşan görüşmeler reddedilmez, 2 kat ücretlenir.

## Karar

- `avatar.realtime` ve `avatar_enrollment.default` = `lemonslice` (yerel ayarda; repodaki
  `providers.yaml` anahtarsız çalışsın diye mock kalır, yorumda nasıl açılacağı yazıyor).
- **Yüz kaydı fotoğrafla:** yüz örneği olarak JPEG/PNG/WebP fotoğraf kabul edilir. Sunucu
  fotoğrafı gerçekten çözüp PNG olarak yeniden kodlar: EXIF/konum silinir, telefon döndürmesi
  uygulanır, sahte dosya reddedilir, uzun kenar 1536 px'e indirilir (§11.7). Rıza hâlâ kodlu
  rıza videosuyla verilir ve kayıt elle incelenir (ADR 0006 değişmedi).
- **Klon yok, fotoğraf bizde:** LemonSlice'ın kayıt adaptörü sağlayıcıya hiçbir şey göndermez;
  yalnızca fotoğraf olduğunu kontrol eder. Görüşme başlarken rızalı fotoğraf şifreli depodan
  okunur (her kullanım `audit_log`'a `biometric.used`), yalnızca o oturum için multipart ile
  LemonSlice'a yüklenir. Herkese açık URL yok. Rıza geri alınınca bir sonraki görüşmede
  gönderilmez, ham dosyalar işçi tarafından imha edilir (§4.2 "varlıklar bizimdir").
- **Sağlayıcıdan bağımsızlık:** domain'de yeni kavram tek bir bayrak: `AvatarProvider.accepts_image`
  ("tek fotoğraftan çalışırım"). Avatarı önceden oluşturulan sağlayıcılar (LiveAvatar, Anam)
  `False` der ve eskisi gibi `avatar_id` kullanır. Başka bir zero-shot sağlayıcıya (ör.
  bitHuman, Faz 7'de kendi sunucumuz) geçiş = yeni adaptör + config değişikliği.
- **EVA'nın yüzü:** `config/media.yaml`'da LemonSlice avatar id'si, herkese açık https görsel
  ya da `file:media/eva.png` (config klasörüne göre yerel görsel; `config/media/` git'e girmez).

## Sonuçlar

- Faz 3'ün açık kalan "yüz avatarı sağlayıcısı" kararı kapandı; yüz kaydı gerçek ortamda
  açılabilir (`provider_available` artık mock görmüyor).
- Her görüşmede kullanıcının fotoğrafı LemonSlice'a gidiyor. LemonSlice'ın yüklenen görseli
  ne kadar sakladığı ve eğitimde kullanıp kullanmadığı dokümanda yok → §15'e eklendi; KVKK yurt
  dışı aktarım (m.9) ve DPIA'da bu aktarım yer almalı.
- Gerçek anahtarla henüz denenmedi (LEMONSLICE_API_KEY yok); adaptör resmî LiveKit eklentisinin
  (livekit-plugins-lemonslice 1.8.8) gönderdiği isteğin aynısını gönderiyor ve sahte API ile test
  edildi.
