"""ORM models. Import everything here so Alembic autogenerate sees all tables."""

from app.models.auth import AuthChallenge, AuthCode, Passkey
from app.models.conversation import Conversation, Message
from app.models.job import Job
from app.models.memory import Memory, MemoryEmbedding
from app.models.persona import Persona
from app.models.session import AuthSession
from app.models.user import User

__all__ = [
    "AuthChallenge",
    "AuthCode",
    "AuthSession",
    "Conversation",
    "Job",
    "Memory",
    "MemoryEmbedding",
    "Message",
    "Passkey",
    "Persona",
    "User",
]
