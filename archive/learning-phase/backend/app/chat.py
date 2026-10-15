from pydantic import BaseModel

class TakeMessage(BaseModel):
    username: str
    user_message: str

class ReplyMessage(BaseModel):
    agent_response: str
    agent: str