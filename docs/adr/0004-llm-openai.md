# ADR 0004: LLM sağlayıcısı OpenAI (GPT)

Tarih: 2026-10-16 · Durum: kabul edildi (sahibin kararı)

## Bağlam

CLAUDE.md §3/§4.2, `LLMProvider` için ilk adaptör olarak Anthropic Claude öneriyordu. Sahip,
EVA'nın OpenAI GPT modelleriyle konuşmasına karar verdi (ücretli anahtar alınacak).

## Karar

- `backend/app/providers/openai_llm.py`: resmi `openai` Python SDK'sı (3.31) ile **Responses API**,
  akışlı. OpenAI'nin güncel dokümanı yeni projeler için Responses'ı öneriyor.
- `config/providers.yaml`'da üç LLM özelliği de `openai`:
  - `chat` → `gpt-6-luna`, effort `low`
  - `realtime` (sesli görüşme) → `gpt-6-luna`, effort `none` (en hızlı)
  - `background` (anı çıkarma) → `gpt-6.1-sol`, effort `medium`
  Bunlar başlangıç tahminidir; kesin seçim eval + gecikme ölçümüyle yapılır (§4.3).
- Gizlilik: her istekte `store=False` (yoksa OpenAI cevabı ≥30 gün saklar). Kullanıcı kimliği
  gönderilmez.
- Hata politikası: zaman aşımı, bağlantı hatası, 5xx ve gerçek istek sınırı (429) tekrar
  denenebilir; kota/bütçe bitti (429 `insufficient_quota` vb.), 400/401/403/404 denenmez.
- Anthropic adaptörü silinmedi; tek satır config değişikliğiyle geri dönülebilir.
- `Effort` tipine `none` eklendi (yalnızca destekleyen modellerde; Claude adaptörü bunu yok sayar).

## Sonuçlar

- `OPENAI_API_KEY` ortam değişkeni gerekir; yoksa `EVA_LLM_PROVIDER_OVERRIDE=mock`.
- OpenAI'nin otomatik prompt cache'i 1024 token'dan kısa sabit baş kısmı önbelleğe almaz;
  güvenlik çekirdeği + persona şu an bundan kısa, yani cache isabeti beklenmez.
- Veri saklama: OpenAI kötüye kullanım kayıtlarını varsayılan 30 gün tutar; sıfır saklama
  (ZDR) ve AB veri yerleşimi OpenAI onayı ister (§12, §15 barındırma kararıyla birlikte).
- Gerçek anahtarla deneme: `tests/` içinde ağsız sahte istemciyle test edildi; gerçek
  çağrı anahtar gelince yapılacak.
