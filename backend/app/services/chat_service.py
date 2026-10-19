"""Metin sohbeti: konuşmalar, mesajlar ve akışlı cevap turu (CLAUDE.md §10).

Sıcak yol kuralı (§2.7; "sıcak yol" = kullanıcının cevabı beklediği kısım): bir geçmiş
okuma, bir LLM akışı, iki yazma. Burada anı çıkarma yapılmaz; o iş arka plan işçisinin.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.telemetry import TurnTimer, record_turn
from app.database import utcnow_after
from app.models.base import new_id
from app.models.conversation import Conversation, Message
from app.models.persona import Persona
from app.models.user import User
from app.persona.compiler import Channel, PersonaCompiler
from app.persona.types import PersonaDefinition, RelationshipState
from app.providers.base import (
    LLMMessage,
    LLMRequest,
    ProviderError,
    StopReason,
    StreamEnd,
    TextDelta,
)
from app.providers.registry import ProviderRegistry
from app.services import legacy_service, memory_extraction, memory_retrieval, persona_service

# --- iletim katmanına (SSE router'ı) gönderilen olaylar --------------------------


@dataclass(frozen=True, slots=True)
class MessageStart:
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Delta:
    text: str


@dataclass(frozen=True, slots=True)
class Done:
    assistant_message_id: uuid.UUID
    stop_reason: StopReason
    interrupted: bool


@dataclass(frozen=True, slots=True)
class Error:
    code: str
    retryable: bool


ChatEvent = MessageStart | Delta | Done | Error


class ConversationNotFoundError(LookupError):
    pass


class ChatService:
    def __init__(
        self, *, registry: ProviderRegistry, compiler: PersonaCompiler, settings: Settings
    ) -> None:
        self._registry = registry
        self._compiler = compiler
        self._settings = settings

    # --- konuşmalar ----------------------------------------------------------------

    async def create_conversation(
        self, db: AsyncSession, user: User, persona_id: uuid.UUID | None
    ) -> Conversation:
        if persona_id is None:
            persona = await persona_service.get_default_eva(db)
        else:
            persona = await persona_service.get_persona_for_user(db, user, persona_id)
        await legacy_service.ensure_can_talk(db, persona, user)
        conversation = Conversation(user_id=user.id, persona_id=persona.id, channel="text")
        db.add(conversation)
        await db.commit()
        return conversation

    async def ensure_can_continue(
        self, db: AsyncSession, user: User, conversation: Conversation
    ) -> None:
        """Akış başlamadan: bu personayla hâlâ konuşulabilir mi (Miras erişimi iptal edilmiş
        olabilir)? Hata ``legacy_service.LegacyNotReadyError``."""
        persona = await db.get(Persona, conversation.persona_id)
        if persona is not None:
            await legacy_service.ensure_can_talk(db, persona, user)

    async def list_conversations(self, db: AsyncSession, user: User) -> list[Conversation]:
        result = await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_conversation(
        self, db: AsyncSession, user: User, conversation_id: uuid.UUID
    ) -> Conversation:
        """Sahiplik kontrolü sorgunun içinde: başkasının konuşması bizim için "yok" sayılır
        (IDOR'a karşı, yani başkasının id'sini deneyip verisine ulaşmaya karşı)."""
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user.id
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        return conversation

    async def list_messages(
        self, db: AsyncSession, user: User, conversation_id: uuid.UUID, limit: int = 200
    ) -> list[Message]:
        conversation = await self.get_conversation(db, user, conversation_id)
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc(), Message.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    # --- sohbet turu ---------------------------------------------------------------

    async def stream_reply(
        self,
        db: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        content: str,
        idempotency_key: str,
    ) -> AsyncIterator[ChatEvent]:
        conversation = await self.get_conversation(db, user, conversation_id)

        replay = await self._find_replay(db, conversation, idempotency_key)
        if replay is not None:
            user_msg, assistant_msg = replay
            yield MessageStart(user_msg.id, assistant_msg.id)
            yield Delta(assistant_msg.content)
            yield Done(assistant_msg.id, "end_turn", assistant_msg.interrupted)
            return

        persona_row = await db.get(Persona, conversation.persona_id)
        if persona_row is None:  # pragma: no cover - FK bunu garanti eder
            raise ConversationNotFoundError(str(conversation_id))
        # Miras'ta erişim her turda yeniden kontrol edilir (iptal anında etkili olsun).
        try:
            definition = await legacy_service.prompt_definition(db, persona_row, user)
        except legacy_service.LegacyNotReadyError as exc:
            raise ConversationNotFoundError(str(conversation_id)) from exc
        history = await self.load_history(db, conversation)

        user_created_at = utcnow_after(history[-1].created_at if history else None)
        user_msg = Message(
            id=new_id(),
            conversation_id=conversation.id,
            role="user",
            content=content,
            channel="text",
            idempotency_key=idempotency_key,
            created_at=user_created_at,
        )
        db.add(user_msg)
        await db.commit()

        assistant_id = new_id()
        yield MessageStart(user_msg.id, assistant_id)

        # Sıcak yoldaki tek hafıza sorgusu (§4.3): mesaja göre ilgili anılar.
        memories = await memory_retrieval.retrieve(
            db, user_id=user.id, persona_id=persona_row.id, query_text=content
        )
        request = self.build_request(
            persona_row, user, history, content, memories, definition=definition
        )
        provider, feature_cfg = self._registry.llm("chat")
        timer = TurnTimer(provider=provider.name, model=feature_cfg.model)
        parts: list[str] = []
        stop_reason: StopReason = "end_turn"
        output_tokens = 0
        interrupted = False

        try:
            async for event in provider.stream(request):
                if isinstance(event, TextDelta):
                    timer.mark_first_token()
                    parts.append(event.text)
                    yield Delta(event.text)
                elif isinstance(event, StreamEnd):
                    stop_reason = event.stop_reason
                    output_tokens = event.output_tokens
        except asyncio.CancelledError:
            interrupted = True
            record_turn(timer, outcome="interrupted")
            await asyncio.shield(
                self._save_assistant(db, conversation, assistant_id, user_created_at, parts, True)
            )
            raise
        except ProviderError as exc:
            record_turn(timer, outcome="provider_error")
            if parts:
                interrupted = True
                await self._save_assistant(
                    db, conversation, assistant_id, user_created_at, parts, True
                )
            yield Error("provider_error", exc.retryable)
            return

        await self._save_assistant(db, conversation, assistant_id, user_created_at, parts, False)
        record_turn(timer, outcome="ok", stop_reason=stop_reason, output_tokens=output_tokens)
        yield Done(assistant_id, stop_reason, interrupted)

    # --- yardımcılar ---------------------------------------------------------------

    async def _find_replay(
        self, db: AsyncSession, conversation: Conversation, idempotency_key: str
    ) -> tuple[Message, Message] | None:
        result = await db.execute(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.idempotency_key == idempotency_key,
            )
        )
        user_msg = result.scalar_one_or_none()
        if user_msg is None:
            return None
        result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.role == "assistant",
                Message.created_at >= user_msg.created_at,
            )
            .order_by(Message.created_at.asc())
            .limit(1)
        )
        assistant_msg = result.scalar_one_or_none()
        if assistant_msg is None:
            return None
        return user_msg, assistant_msg

    async def load_history(self, db: AsyncSession, conversation: Conversation) -> list[Message]:
        limit = self._settings.chat_history_turns * 2
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id)
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    def build_request(
        self,
        persona_row: Persona,
        user: User,
        history: Sequence[Message],
        content: str,
        memories: Sequence[str] = (),
        *,
        feature: str = "chat",
        channel: Channel = "text",
        definition: PersonaDefinition | None = None,
    ) -> LLMRequest:
        """Persona + ilişki + anılar + geçmiş + yeni mesaj -> LLM isteği. Sesli görüşme de
        aynı yolu kullanır (``feature="realtime"``, ``channel="voice"``)."""
        if definition is None:
            definition = persona_service.definition_of(persona_row)
        relationship = RelationshipState(stage="introduction", user_display_name=user.display_name)
        prompt = self._compiler.compile(
            definition, relationship=relationship, retrieved_memories=memories, channel=channel
        )
        _, feature_cfg = self._registry.llm(feature)
        turns = [(m.role, m.content) for m in history]
        turns.append(("user", content))
        messages = _normalize_turns(turns)
        return LLMRequest(
            model=feature_cfg.model,
            system=prompt.system,
            messages=tuple(messages),
            max_tokens=feature_cfg.max_tokens,
            effort=feature_cfg.effort,
        )

    async def _save_assistant(
        self,
        db: AsyncSession,
        conversation: Conversation,
        assistant_id: uuid.UUID,
        user_created_at: datetime,
        parts: list[str],
        interrupted: bool,
    ) -> None:
        db.add(
            Message(
                id=assistant_id,
                conversation_id=conversation.id,
                role="assistant",
                content="".join(parts),
                channel="text",
                interrupted=interrupted,
                created_at=utcnow_after(user_created_at),
            )
        )
        conversation.updated_at = conversation.updated_at  # dokun -> onupdate tetiklenir
        db.add(conversation)
        # Sohbet sustuktan sonra anı çıkarma işi; cevapla aynı commit'te (ADR 0003).
        # İlk token'dan SONRA çalışır, yani cevabın başlama hızını etkilemez.
        await memory_extraction.schedule(
            db, conversation, idle_s=self._settings.memory_extract_idle_s
        )
        await db.commit()


def _normalize_turns(turns: Sequence[tuple[str, str]]) -> list[LLMMessage]:
    """Sağlayıcılar, user ile başlayıp user/assistant diye sırayla değişen turlar ister.

    Baştaki assistant turları atılır; art arda aynı rolden gelen turlar (yarıda kesilmiş
    bir cevap, tek başına user mesajı bırakan başarısız bir tur) tek turda birleştirilir.
    """
    out: list[LLMMessage] = []
    for role, content in turns:
        if role not in ("user", "assistant") or not content.strip():
            continue
        if not out and role == "assistant":
            continue
        if out and out[-1].role == role:
            out[-1] = LLMMessage(out[-1].role, out[-1].content + "\n" + content)
        else:
            out.append(LLMMessage("user" if role == "user" else "assistant", content))
    return out
