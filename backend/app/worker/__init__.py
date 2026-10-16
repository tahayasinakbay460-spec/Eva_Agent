"""Arka plan işçisi (CLAUDE.md §3, ADR 0003): anıları vektöre çevirme, sohbetten anı çıkarma.

Ayrı süreç olarak:  uv run python -m app.worker
Geliştirmede API'nin içinde de çalışır (EVA_ENV=dev, ``Settings.run_worker_inprocess``).
"""
