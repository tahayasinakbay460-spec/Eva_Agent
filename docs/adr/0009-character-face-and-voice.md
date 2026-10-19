# ADR 0009: Karakterlerin yüzü ve sesi

Tarih: 2026-10-19 · Durum: kabul edildi (sahibin 2026-10-19 kararı; demo aşaması)

## Bağlam

Karakter Stüdyosu'nda (Faz 4) karakterler herkese açık olabiliyor ve romantik karakterlere izin
var. Sahibin kararı: kullanıcı karakterine istediği yüzü verebilir: kendi fotoğrafı, bir çizim /
çizgi film karakteri ya da başka birinin fotoğrafı. +18 içerik yok. Ses hazır seslerden seçilir.
Sahip, başka kişilerin fotoğrafıyla ilgili hukuki konuları (rıza, KVKK) lansmandan önce ayrıca ele
alacağını belirtti. Claude, CLAUDE.md §2 kural 2 ile çeliştiğini ve riskleri (izinsiz yüz,
romantik karakter + herkese açık paylaşım, reşit olmayan fotoğrafı) iki kez yazdı; karar sahibin.

## Karar (şu an uygulanan)

- **Karakterin yüzü:** kullanıcının yüklediği tek bir görsel (JPEG / PNG / WebP, ≤ 10 MB). Yüklemeden
  önce kullanıcı beyanı zorunlu: "görseli kullanma hakkım var, görseldeki kişi 18 yaşından büyük,
  karakter +18 içerik için kullanılamaz" (`rights_confirmed=true`, yoksa 422). Beyan denetim
  kaydına yazılır (`character.face_set`).
- **İşleme:** biyometrik yüklemeyle aynı hat: sihirli baytlar, çözüp PNG'ye yeniden kodlama (EXIF /
  konum silinir), boyut sınırı. Görsel karakter sahibinin veri anahtarıyla şifreli, `media` kovasında.
  Sahibi hesabını silerse kripto-silme ile okunamaz olur.
- **Görüşme:** fotoğraftan çalışan avatar sağlayıcısına (LemonSlice, ADR 0007) yalnızca görüşme
  sırasında gönderilir; sağlayıcıda kalıcı avatar oluşturulmaz. Yüz seçicide ayrılmış anahtar
  `persona`; yüzü olan karakterde varsayılan budur.
- **Ses:** `config/media.yaml` hazır seslerinden biri (`personas.voice_key`), boşsa EVA'nın
  varsayılanı. Kullanıcı kendi onaylı sesini/yüzünü (`own`, ADR 0008) her karakterde seçebilir.
- **Görünürlük:** `personas.visibility` = `public` (varsayılan) | `private`. Herkese açık karakterle
  herkes yazışır ve görüşür; yalnızca sahibi düzenler/siler.
- **Kırmızı çizgiler değişmedi:** güvenlik çekirdeği gerçek bir kişinin kimliğiyle cinsel içerik,
  açık cinsel içerik ve reşit olmadığını söyleyen kullanıcıyla flört üretmez (eval'lerde ölçülüyor).

## Lansmandan önce açık (CLAUDE.md §15)

- Başka bir gerçek kişinin fotoğrafı: o kişinin rızası (davet linki) mi, bildir-kaldır mı?
- Herkese açık karakterler için bildir / engelle ve telif kaldırma süreci.
- Reşit olmayan yüzüne karşı otomatik kontrol (yaş tahmini) ya da admin incelemesi.
- `config/blocked_franchises.yaml` ve `config/sensitive_figures.yaml` (Faz 4 adım 2).
- LemonSlice'ın çizimlerle davranışı güncel dokümandan doğrulanacak.

## Sonuçlar

- Migration `a3f9c2d17b40`: `personas.visibility`, `face_blob_key`, `face_media_type`, `voice_key`.
- Uçlar: `GET/POST /characters`, `GET/PUT/DELETE /characters/{id}`, `PUT/GET/DELETE
  /characters/{id}/face`. Web: `/kesfet`, `/kesfet/yeni`, `/chat?karakter=`, `/gorusme?karakter=`.
