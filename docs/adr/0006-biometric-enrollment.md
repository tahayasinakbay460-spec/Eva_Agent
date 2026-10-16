# ADR 0006: Rızalı ses/yüz kaydı — elle inceleme, tek kayıt tablosu, değiştirilemez rıza kaydı

Tarih: 2026-10-16 · Durum: kabul edildi (Faz 3; sahibin 2026-10-16 kararlarıyla)

## Bağlam

CLAUDE.md §11.3 rızayı amaç bazlı, kişinin kendisinin verdiği, doğrulanmış ve geri alınabilir
ister; rıza videosundaki yüz/ses örneklerle eşleşmeli, reşit olmayanlar engellenmeli. Yüz
eşleştirme ve yaş tahmini için seçilmiş bir sağlayıcı yok.

## Karar

- **Her kayıt elle incelenir (sahibin kararı).** Kayıt gönderilince `pending_review` olur; bir
  admin örnekleri ve rıza videosunu izleyip dört maddeyi tek tek onaylar (reşit, aynı kişi, kod
  doğru, rıza açık). Onay olmadan sağlayıcıda hiçbir klon oluşturulmaz. Prod'da kimse kendi
  kaydını onaylayamaz; dev'de tek kişilik geliştirme için izinli ve denetim kaydında işaretli.
- **Rıza doğrulaması:** her kayıt için rastgele 6 haneli kod; kişi kodu içeren cümleyi kamerada
  sesli okur (canlılık + tekrar oynatma koruması). Ses kaydı için de rıza videoludur (yüz + ses).
- **Tek tablo:** CLAUDE.md'deki `voice_profiles` / `avatar_profiles`, `biometric_enrollments`
  tablosunda `kind` (voice | face) ile tutulur; sağlayıcı eşlemesi `provider_assets`'te.
- **Rıza:** `consents` (bugünkü durum, amaç bazlı) + `consent_records` (yalnızca eklenir:
  olay, metin sürümü, metin özeti, rıza videosunun özeti). `audit_log` da yalnızca eklenir.
  İkisinde de ORM seviyesinde güncelleme/silme engelli.
- **Dosyalar:** ham gövde olarak yüklenir (multipart bağımlılığı yok); boyut sınırı akışta, tür
  sihirli baytlarla doğrulanır; kullanıcı başına veri anahtarıyla şifreli depoda, ayrı
  "biometric" kovasında.
- **Geri alma:** istek anında durum `revoked`; her kullanım (önizleme, görüşme) durumu o an
  kontrol eder. İşçi klonu sağlayıcıdan siler (idempotent, tekrar denenir) ve dosyaları imha
  eder; rıza kaydı ve özetler kanıt olarak kalır.
- **Önizleme:** yalnızca sabit cümlelerle (klon sesle keyfi konuşma üretilemez, §11.3).
- **Admin:** `users.role`; API'den verilemez, sadece `scripts/make_admin.py` ile.

## Sonuçlar

- Gerçek ortamda (staging/prod) sağlayıcı `mock` iken kayıt başlatılamaz (`enrollment_unavailable`).
- **LiveAvatar'da özel avatar oluşturma API'si yok** (2026-10-16 itibarıyla yalnızca panelden) ve
  silme "yumuşak silme". Yüz kaydı akışı (rıza, inceleme, şifreli saklama, geri alma) çalışıyor;
  sağlayıcıda avatar oluşturma adımı şimdilik sahte adaptörde. Açık karar: LiveAvatar/HeyGen'den
  kurumsal API ve kalıcı silme teyidi, ya da başka bir avatar sağlayıcısı (§15).
- Rıza kanıtının hesap silindikten sonra saklanma süresi hukukçu görüşüne bağlı (§12).
