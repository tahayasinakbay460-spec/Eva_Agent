"""İş türlerinin adları. Ayrı dosyada: servisler iş eklerken işleyicileri (ve onların
bağımlılıklarını) içe aktarmak zorunda kalmasın, döngüsel import olmasın.
"""

EMBED_MEMORY = "embed_memory"
EXTRACT_MEMORIES = "extract_memories"
# Onaylanan biyometrik kayıt için sağlayıcıda klon oluştur (Faz 3).
BIOMETRIC_CREATE_ASSET = "biometric_create_asset"
# Geri alınan / reddedilen kaydın klonunu sağlayıcıdan sil, dosyalarını imha et.
BIOMETRIC_PURGE = "biometric_purge"
