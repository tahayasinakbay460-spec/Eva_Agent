# ADR 0003: Arka plan işleri için veritabanı kuyruğu (şimdilik Redis yerine)

Tarih: 2026-10-16 · Durum: kabul edildi (sahibin onayıyla)

## Bağlam

CLAUDE.md §3 arka plan işleri için "Python worker + Redis tabanlı kuyruk" diyor.
Faz 1'de anıyı vektöre çevirme ve sohbetten anı çıkarma gibi işler arka planda
çalışmalı (§2.7: sıcak yolda bloklayan iş yok). Geliştirme bilgisayarında Redis ve
Docker yok.

## Karar

İşler mevcut veritabanındaki `jobs` tablosunda tutulur:

- **Ekleme:** iş, onu doğuran değişiklikle **aynı commit'te** yazılır. Anı kaydedildiyse
  "vektöre çevir" işi de kesin vardır; biri olup diğeri kaybolamaz.
- **Kapma:** işçi bekleyen bir işi `UPDATE ... WHERE status='pending'` ile kendine alır.
  Aynı işi iki işçi aynı anda alamaz; satırı ilk güncelleyen kazanır.
- **Tekrar deneme:** hata olursa iş artan bekleme süresiyle (20 sn, 40 sn, 80 sn...)
  yeniden denenir; deneme hakkı bitince `failed` olur. Hata kaydında sadece hata türü
  tutulur, içerik tutulmaz (§2.6).
- **Çökme:** 10 dakikadan uzun süredir "çalışıyor" görünen iş (işçi çökmüş) tekrar
  sıraya döner. İşler bu yüzden tekrar çalıştırılabilir (idempotent) yazılır.
- **Erteleme ve tekilleştirme:** `run_at` ile ileri tarihli iş, `dedupe_key` ile "aynı
  iş zaten sırada mı?" kontrolü (ör. sohbet bitince bir kez anı çıkar).
- **Nerede çalışır:** `uv run python -m app.worker` ayrı bir süreç olarak. Geliştirmede
  ayrıca terminal açmamak için `EVA_ENV=dev` iken API'nin içinde de çalışır
  (`EVA_WORKER_INPROCESS` ile kapatılabilir). İşçi kodu `backend/app/worker/` altında
  (ADR 0001 klasör eşlemesi), modelleri API ile paylaşır.

## Sonuçlar

- Kurulacak yeni bir şey yok; SQLite'ta da Postgres'te de çalışır.
- Kuyruk `app/worker/queue.py` arkasında; Redis'e geçiş sadece bu modülü değiştirir.
  Yük arttığında (çok sayıda işçi, saniyede yüzlerce iş) Redis'e geçilmeli.
- Postgres'te ileride `FOR UPDATE SKIP LOCKED` ile kapma hızlandırılabilir.
