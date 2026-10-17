# ADR 0008: EVA'nın sesi ve yüzü kullanıcının seçimi — katalog + kendi klonu, birbirinden bağımsız

Tarih: 2026-10-17 · Durum: kabul edildi (sahibin 2026-10-17 kararı)

## Bağlam

Sahibin istediği: EVA'nın kendine özgü bir sesi olsun (varsayılan); uygulamada hazır yüzler ve
hazır sesler de olsun; kullanıcı EVA'yı istediği yüzle ve istediği sesle kullanabilsin. Kendi
fotoğrafını yükleyen kullanıcı, bu fotoğrafı istediği hazır sesle ya da kendi klon sesiyle
eşleştirebilsin. Önceki modelde tek bir bayrak vardı (`use_my_media`): ya personanın sesi + yüzü
ya da kullanıcının kendi sesi + yüzü. Karışık kullanım mümkün değildi.

## Karar

- **Katalog:** `config/media.yaml` → `voices` ve `avatars` (her biri: ad + sağlayıcı başına id),
  `personas` (persona varsayılanları; EVA = `eva` sesi ve `eva` yüzü). Bir seçenek yalnızca seçili
  sağlayıcıda id'si varsa listelenir. Yerel görselli yüzler (`file:`) yalnızca fotoğraftan çalışan
  avatar sağlayıcısında. Anahtar `own` ayrılmıştır.
- **Seçim:** `media_preferences` (kullanıcı + persona başına `voice_key`, `avatar_key`; boş =
  varsayılan). `own` yalnızca rızası onaylanmış, aktif ve şu anki sağlayıcıyla oluşturulmuş bir
  kayıt varsa kabul edilir.
- **Görüşme:** seçim görüşme başlarken `call_sessions.voice_key` / `avatar_key`'e kopyalanır;
  görüşme boyunca değişmez. `own` olan taraf için rıza her turda yeniden kontrol edilir (geri
  alınırsa görüşme biter). `media_source` sütunu kaldırıldı; eski kayıtlar migration'da taşındı.
- **Uçlar:** `GET /media/options`, `PUT /media/preferences`, `POST /media/voices/{key}/preview`
  (yalnızca hazır sesler, sabit cümle; kendi sesin önizlemesi `/biometrics/voice/preview`'da
  kalır), `GET /media/avatars/{key}/image` (yerel katalog görselleri için küçük resim).
- **Hazır sesler:** ElevenLabs'in ücretsiz planda da API'den kullanılabilen hazır sesleri
  (EVA = Jessica, özgün ses tasarlanana kadar). Hazır yüzler sahibin ekleyeceği lisanslı
  görsellerle (`config/media/`, git'e girmez).

## Sonuçlar

- Kendi fotoğrafı + hazır ses, hazır yüz + kendi sesi, ikisi de kendi: hepsi mümkün.
- Karakter Stüdyosu'nda (Faz 4) karakterler de aynı kataloğu ve aynı seçim tablosunu kullanır
  (`persona_id` zaten tabloda).
- Hazır yüz yoksa görüntülü görüşme açıkça "hazır yüz yok" der; sahte veri gösterilmez.
