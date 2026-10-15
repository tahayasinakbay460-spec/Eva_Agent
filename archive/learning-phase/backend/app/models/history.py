from app.database import Base, engine
from sqlalchemy import Column, Integer, String, DateTime

class History(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key =True, index=True)
    username = Column(String, index=True)
    user_message = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    agent_response = Column(String, index=True)