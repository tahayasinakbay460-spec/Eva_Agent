# ADR 0011: Miras — vefat sonrası mod ve iki modun ayrımı

Tarih: 2026-10-19 · Durum: kabul edildi (sahibin 2026-10-19 kararları; yöntem seçimi Claude'a bırakıldı)

## Bağlam

Sahibin vizyonu: Miras bir "bilinç aktarımı"dır ve iki modu vardır (Miras sayfasında belirgin ayrı):

1. **Yaşarken paylaş** (ADR 0010): kişi anahtarla seçtiği yakınının Karakterler bölümünde görünür;
   iki taraf da bitirebilir, sahip yeniden anahtar verebilir. EVA kişiyi yeterince tanımalı:
   Miras'a dahil en az 30 anı + EVA'ya yazılmış en az 100 mesaj.
2. **Vefat sonrası:** sahip alıcılarını önceden belirler; vefatında anahtarlar **otomatik** gider.
   Sahibin kararı: 6 aylık hareketsizlik süreci; yöntemin geri kalanı Claude'a bırakıldı.
   Alıcı vefat sonrası Miras'ı silerse 2–3 kez "emin misiniz" + e-posta kodu; silse bile karakter
   sistemde yaşamaya devam eder, geri getirmek için bizimle iletişime geçer.

## Karar

- **Hazırlık (sahip):** adım-yukarı + vefat sonrası rıza metni + yayınlanmış sürüm + onaylı ses ve
  yüz + tanınma eşiği. En fazla 5 vefat sonrası alıcı (e-posta). Liste her an değiştirilebilir ya
  da tamamen kapatılabilir. Durum: `armed` (kurulu) | `warning` (uyarı süreci) | `activated` |
  `off`.
- **Etkinlik:** her kimlik doğrulamalı istekte `users.last_active_at` güncellenir (saatte en çok bir
  kez yazılır). Uyarı sürecindeyken sahip herhangi bir şekilde giriş yaparsa süreç iptal olur ve
  `armed`'a döner.
- **Tetikleyiciler (Claude'un seçimi: ikisi de, ikisi de aynı uyarı sürecinden geçer):**
  1. **Hareketsizlik:** `last_active_at` 180 günden eskiyse uyarı süreci başlar.
  2. **Vefat bildirimi:** yalnızca belirlenmiş bir alıcı (doğrulanmış hesap e-postası listede) bir
     belge yükleyebilir; admin elle inceler; onaylanırsa uyarı süreci hemen başlar.
- **Uyarı süreci:** 14 gün; sahibe 0., 7. ve 13. günlerde sabit şablonlu e-posta ("Miras'ın
  açılmak üzere; sen değilsen giriş yap"). Bu sürede hiç giriş olmazsa **etkinleşir**.
- **Etkinleşme:** her alıcı için vefat sonrası anahtar üretilir (`legacy_grants.mode =
  posthumous`, 365 gün geçerli) ve alıcıya otomatik e-postayla gider. Kullanma akışı ADR 0010 ile
  aynı (anahtar + e-posta kodu).
- **Tarama:** işçide kendini yeniden sıraya koyan saatlik iş (`legacy_posthumous_sweep`); açılışta
  yoksa eklenir. İdempotent: aynı uyarı iki kez gitmez, aynı alıcıya iki anahtar gitmez.
- **Alıcının silmesi (vefat sonrası):** arayüzde 3 onay + `POST /legacy/shared/{id}/delete/start`
  (e-postaya kod) + `/delete/verify`. Yalnızca alıcının erişimi `deleted` olur; persona, sürüm ve
  alıcının geçmişi silinmez. Geri getirme: admin `POST /admin/legacy/access/{id}/restore`.
  Yaşarken paylaş modunda alıcının silmesi ADR 0010'daki gibi kalır (kendi geçmişi de silinir).

## Sonuçlar

- Yeni: `users.last_active_at`, `legacy_posthumous` (sahip başına), `legacy_heirs`,
  `legacy_death_reports`, `legacy_grants.mode`, `legacy_access.mode`.
- Yanlış etkinleşme riski: 6 ay + 14 gün + 3 uyarı; belgeyle bildirim de aynı uyarılardan geçer.
- Açık: SMS ile uyarı (sağlayıcı seçilince), vefat eden sahibin Miras'ını kalıcı silme talebini kim
  yapabilir (§15; şimdilik yalnızca admin, hukukçu görüşüyle netleşecek).
