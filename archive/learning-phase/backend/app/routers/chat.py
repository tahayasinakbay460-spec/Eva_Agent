from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.schemas.chat import TakeMessage ,ReplyMessage
from fastapi import Depends
from app.database import get_db
from app.services.agent import get_agent_response
from app.services.agent import get_agent_response
from app.models.history import History

router = APIRouter(prefix="/", tags=["chat"])

@router.post("/chat")
def get_chat(chat_message: TakeMessage, db=Depends(get_db))-> ReplyMessage:
    return get_agent_response(chat_message, db)

@router.get("/history")
def get_history(db=Depends(get_db))-> list[TakeMessage]:
    history = db.query(History).all()
    return history