# ADR 0009: Karakterlerin yüzü ve sesi — katalog, kendi yüzün, çizim

Tarih: 2026-10-19 · Durum: kabul edildi (sahibin 2026-10-19 kararı)

## Bağlam

Karakter Stüdyosu'nda (Faz 4) karakterler herkese açık olacak ve romantik karakterlere izin
var. Sahibin istediği: karakterin yüzü hazır bir yüz, kullanıcının **kendi yüzü** ya da bir
**çizgi film / çizim** karakteri olabilsin. Tarihi figürler (Fatih Sultan Mehmet, Kanuni Sultan
Süleyman, Selahaddin Eyyubi) da hazır karakterler arasında.

## Karar

Bir karakterin yüzü ve sesi birbirinden bağımsız olarak şu kaynaklardan biridir:

| Kaynak | Yüz | Ses | Kural |
|---|---|---|---|
| `catalog` | `config/media.yaml` hazır yüzleri | hazır sesler | serbest |
| `own` | karakteri oluşturanın onaylı kendi fotoğrafı | onaylı kendi klon sesi | ADR 0006/0007 rıza akışı + ayrı "karakter olarak kullanım" rızası (§11.3) |
| `illustration` | kullanıcının yüklediği çizim / çizgi film görseli | — (ses katalogdan ya da `own`) | hak beyanı + telif engel listesi + admin incelemesi |

- **`own` herkese açık karakterde:** başka kullanıcılar da o yüzle/sesle konuşacağı için ayrı
  bir rıza amacı gerekir (`consents.purpose = character_public`). Sahibi bu rızayı geri alınca
  karakter anında katalog yüze/sese düşer, devam eden görüşmeler ADR 0008'deki gibi biter.
  Gerçek kişinin kimliğiyle cinsel içerik yasağı (§2) sahibinin kendi yüzü için de geçerlidir;
  flört serbest, açık cinsel içerik yok.
- **`illustration`:** mevcut yükleme hattından geçer (magic bytes, EXIF temizleme, boyut).
  Biyometrik veri değildir ama karakter herkese açık olduğu için admin incelemesi onaylamadan
  yalnızca sahibine görünür. İnceleyici gerçek bir insan fotoğrafı görürse reddeder ve kullanıcıyı
  `own` (kendi yüzüyse) ya da davet rızasına (başkasıysa) yönlendirir. Telifli karakterler
  (`config/blocked_franchises.yaml`) ve hassas figürler engelli.
- **Başka bir gerçek kişi:** o kişinin davet linkiyle kendi rızasını vermesi (Faz 4'ün 8. adımı).
- **Tarihi figürler:** yüz yalnızca kamu malı görsellerden (`illustration` gibi incelenir), ses
  tasarlanmış hazır ses; gerçek kayıtlardan klon yok (§9.1).
- **Veri:** `persona_media` (persona başına varsayılan: `avatar_source`, `avatar_ref`,
  `voice_source`, `voice_ref`, `review_status`). Kullanıcının kendi seçimi `media_preferences`'ta
  kalır (ADR 0008); başkasının `own` yüzü/sesi seçenek olarak hiç listelenmez.
- **Avatar sağlayıcısı:** görsel tabanlı sağlayıcı (LemonSlice, ADR 0007) `own` ve
  `illustration` için aynı yolu kullanır: görsel bizde şifreli durur, her görüşmede gönderilir.
  Çizimlerle çalışıp çalışmadığı entegrasyondan önce güncel dokümandan doğrulanacak (§2 kural 9).

## Sonuçlar

- Kullanıcı kendi yüzüyle ya da bir çizimle karakter oluşturabilir. Herkese açık karakter için
  ek rıza ya da inceleme gerekir.
- Yeni tablo ve migration gerekir (`persona_media`); rıza amaçlarına `character_public` eklenir.
- Admin inceleme kuyruğuna çizim görselleri de düşer (yük artar; otomatik ön kontrol §15'te açık).
