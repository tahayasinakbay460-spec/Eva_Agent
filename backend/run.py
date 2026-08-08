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
import uvicorn   # port kapsında durur ve gelen istekleri alır 
from app.config import Config

#from app.main import app // bu main.py deki app degişkenini getirmenin uzun hali 
# eger main dosyasının adı app degil de eva olsaydı o zaman "app.eva:eva" yazıcaktık
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",          # "dosya:FastAPI_instance_adı"   // app yazsaydık sadece o zaman app in yerini bilmeyecekti 
        host="0.0.0.0",
        port=Config.APP_PORT,
        reload=Config.DEBUG,     # Debug modda kod değişince otomatik restart
        log_level="info"
    )
