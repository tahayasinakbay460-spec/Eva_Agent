"""Ajanı çalıştırır:

    cd realtime
    uv run python -m eva_realtime download-files   # bir kez: VAD ve tur sonu modelleri
    uv run python -m eva_realtime dev              # geliştirme (kod değişince yeniden başlar)

LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET ve backend'in diğer ayarları
``backend/.env``'den okunur.
"""

from livekit.agents import cli

from eva_realtime.agent import server

if __name__ == "__main__":
    cli.run_app(server)
