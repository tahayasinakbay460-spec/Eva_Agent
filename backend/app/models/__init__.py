"""ORM modelleri. Alembic autogenerate tüm tabloları görsün diye hepsi burada import edilir."""

from app.models.auth import AuthChallenge, AuthCode, Passkey
from app.models.biometric import (
    AuditLog,
    BiometricEnrollment,
    Consent,
    ConsentRecord,
    EnrollmentSample,
    ProviderAsset,
)
from app.models.call import CallSession, TurnLatency
from app.models.conversation import Conversation, Message
from app.models.job import Job
from app.models.legacy import LegacyAccess, LegacyGrant, LegacyRedeemFailure, PersonaVersion
from app.models.media import MediaPreference
from app.models.memory import Memory, MemoryEmbedding
from app.models.persona import Persona
from app.models.session import AuthSession
from app.models.storage import UserDataKey
from app.models.user import User

__all__ = [
    "AuditLog",
    "AuthChallenge",
    "AuthCode",
    "AuthSession",
    "BiometricEnrollment",
    "CallSession",
    "Consent",
    "ConsentRecord",
    "Conversation",
    "EnrollmentSample",
    "Job",
    "LegacyAccess",
    "LegacyGrant",
    "LegacyRedeemFailure",
    "MediaPreference",
    "Memory",
    "MemoryEmbedding",
    "Message",
    "Passkey",
    "Persona",
    "PersonaVersion",
    "ProviderAsset",
    "TurnLatency",
    "User",
    "UserDataKey",
]
