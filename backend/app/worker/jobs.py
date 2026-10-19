"""İş türlerinin adları. Ayrı dosyada: servisler iş eklerken işleyicileri (ve onların
bağımlılıklarını) içe aktarmak zorunda kalmasın, döngüsel import olmasın.
"""

EMBED_MEMORY = "embed_memory"
EXTRACT_MEMORIES = "extract_memories"
# Onaylanan biyometrik kayıt için sağlayıcıda klon oluştur (Faz 3).
BIOMETRIC_CREATE_ASSET = "biometric_create_asset"
# Geri alınan / reddedilen kaydın klonunu sağlayıcıdan sil, dosyalarını imha et.
BIOMETRIC_PURGE = "biometric_purge"
# Miras: sahibin anılarından ve mesajlarından kişilik taslağı (Faz 5).
LEGACY_SYNTHESIZE = "legacy_synthesize"
# Miras: vefat sonrası tarama (hareketsizlik, uyarılar, etkinleşme); saatlik, kendini yeniler.
LEGACY_POSTHUMOUS_SWEEP = "legacy_posthumous_sweep"
