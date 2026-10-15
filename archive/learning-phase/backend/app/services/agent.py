from app.schemas.chat import ReplyMessage, TakeMessage
from app.core.config import API_KEY
from groq import Groq
from app.core.system_propmt import EVA_SYSTEM_PROMPT, MEMORY_INJECTION_TEMPLATE
from app.database import get_db, utcnow
from app.models.history import History

global client
client = Groq(api_key=API_KEY)

def get_agent_response(chat_message: TakeMessage, db) -> ReplyMessage:
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": EVA_SYSTEM_PROMPT},
            {"role": "user", "content": chat_message.user_message}
        ]
    )
    print("Agent response:", response.choices[0].message.content)

    db.add(History(username=chat_message.username, user_message=chat_message.user_message, timestamp=utcnow(), agent_response=response.choices[0].message.content))
    db.commit()

    return {"agent": "Eva", "agent_response": response.choices[0].message.content}
