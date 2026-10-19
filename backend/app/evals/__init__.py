"""Persona kalite kapısı: karakter bütünlüğü ve red-team senaryoları (CLAUDE.md §7, §11.5, §13).

Senaryolar depo kökündeki ``evals/`` klasöründe YAML olarak durur; bu paket onları okur,
persona modeline gönderir ve cevabı kurallarla (+ isteğe bağlı bir LLM hakemiyle) puanlar.
Çalıştırma:  cd backend && uv run python -m app.evals
"""
