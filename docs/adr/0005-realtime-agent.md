# ADR 0005: Sesli görüşme ajanı — ayrı `realtime/` projesi, LiveKit Agents + kendi adaptörlerimiz

Tarih: 2026-10-16 · Durum: kabul edildi (Faz 2; sahibin "önce Faz 2, sonra 3" kararıyla)

## Bağlam

CLAUDE.md §3/§4.3 gerçek zamanlı yol için LiveKit (WebRTC) + LiveKit Agents (Python) diyor.
LiveKit Agents 1.8 ağır bağımlılıklar getiriyor (onnxruntime, av, numpy, kendi OpenTelemetry
sürüm sabitlemesi) ve Windows'ta işleri süreç yerine thread'de çalıştırıyor.

## Karar

- **Ayrı uv projesi:** `realtime/` (`eva_realtime` paketi). Backend'i yerel, düzenlenebilir
  paket olarak kullanır (`eva-backend = { path = "../backend" }`); persona, hafıza,
  sağlayıcılar ve veritabanı kodu tek yerde kalır. Ağır bağımlılıklar backend'e bulaşmaz;
  backend'e yalnızca hafif `livekit-api` (token üretmek için) eklendi.
- **Sağlayıcı sınırı (§2.4):** LiveKit'in STT/LLM/TTS sınıfları yalnızca
  `eva_realtime/adapters.py`'de görünür. İçeride iş her zaman bizim arayüzlerimizle yapılır;
  sağlayıcı değiştirmek `providers.yaml` değişikliğidir. Resmî `livekit-plugins-*` sağlayıcı
  eklentileri (ElevenLabs, OpenAI, LiveAvatar) kullanılmaz.
- **LiveKit ne yapar:** ses taşıma, VAD (Silero), Türkçe destekli ses tabanlı tur sonu modeli
  (`inference.TurnDetector`, kendi sunucumuzda CPU'da), söz kesme (barge-in), ölçümler.
- **Geçmiş bizde:** LLM isteği her turda LiveKit'in tuttuğu geçmişten değil, veritabanından
  metin sohbetiyle aynı kurallarla kurulur (`CallTurns.prepare_reply`). Böylece metinden sese
  geçince konuşma kaldığı yerden sürer (§5.3).
- **Tur sonu ↔ STT:** OpenAI `gpt-live-transcribe` kendi VAD'ını yapmaz; LiveKit'in VAD'ı
  "kullanıcı sustu" deyince STT akışına `SpeechBoundary` konur ve bölüm kesinleşir.
- **Güvenlik:** tarayıcının token'ı tek odaya, 2 dakikalığına, yalnızca mikrofon yayınına izin
  verir; ajan çağrısı ve görüşme id'si token'ın içinde imzalıdır (tarayıcı değiştiremez). Ajan
  yalnızca token sahibinin sesini dinler (`participant_identity`).
- **Maliyet:** "kullanıcı bitirmeden cevap üretmeye başlama" (preemptive generation) kapalı;
  gecikme ölçülünce yeniden değerlendirilecek.

## Sonuçlar

- Çalıştırmak için LiveKit sunucusu gerekir: lokalde `livekit-server --dev` (Windows ikili
  dosyası var) ya da LiveKit Cloud'un ücretsiz katmanı. Ayarlar `backend/.env`'de
  (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`).
- Prod Linux'ta çalışmalı (Windows'ta işler thread'de koşar).
- CI'da ayrı `realtime` işi var.
- Sonraki adımlar: ElevenLabs'te görüşme boyu tek WebSocket (multi-stream-input) ile TTS
  bağlantı süresini sıfırlamak; gerçek anahtarlarla gecikme ölçümü (§4.4).
