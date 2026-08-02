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
import uvicorn
from app.config import Config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",          # "dosya:FastAPI_instance_adı"
        host="0.0.0.0",
        port=Config.APP_PORT,
        reload=Config.DEBUG,     # Debug modda kod değişince otomatik restart
        log_level="info"
    )
