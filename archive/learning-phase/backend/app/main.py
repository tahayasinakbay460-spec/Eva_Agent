from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.routers import chat
from app.database import Base, engine ,get_db
from app.models.history import History as history_model

Base.metadata.create_all(bind=engine)


app = FastAPI()
app.add_middleware(CORSMiddleware,
                    allow_origins=["*"], 
                    allow_credentials=True, 
                    allow_methods=["*"], 
                    allow_headers=["*"])

app.include_router(chat.router)
@app.get("/")
def health_check():
    return {"message": "Backend is running!"}
print("benim adım:", repr(__name__))
if __name__ == "__main__":
    
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
