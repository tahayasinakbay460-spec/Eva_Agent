"""
Eva Backend - Giriş Noktası (FastAPI + Uvicorn)
================================================
Başlatmak için terminalde: python run.py

📚 Flask vs FastAPI başlatma:
    Flask:   app.run(host=..., port=...)
    FastAPI: uvicorn.run("app.main:app", host=..., port=...)
    
    Uvicorn = ASGI sunucusu (Flask'ın kullandığı Werkzeug'un karşılığı)
    ASGI async destekler, WSGI desteklemez.
"""
import os
import sys

# ─── Windows UTF-8 Encoding Fix ────────────────────────────────────────
# Windows'un varsayilan kodlamasi CP1254 (Turkce) veya CP1252 (Bati).
# Emoji ve bazi ozel karakterler bu kodlamalarda yok → print() patlar.
# PYTHONUTF8=1 tum Python surecleri icin UTF-8 zorlar.
# Bu ortam degiskeni uvicorn'un reload ile olusturdugu
# alt sureclere de aktarilir.
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import uvicorn   # port kapsinda durur ve gelen istekleri alir
from app.config import Config

#from app.main import app // bu main.py deki app degiskenini getirmenin uzun hali
# eger main dosyasinin adi app degil de eva olsaydi o zaman "app.eva:eva" yazicaktik
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",          # "dosya:FastAPI_instance_adi"
        host="0.0.0.0",
        port=Config.APP_PORT,
        reload=Config.DEBUG,     # Debug modda kod degisince otomatik restart
        log_level="info"
    )
