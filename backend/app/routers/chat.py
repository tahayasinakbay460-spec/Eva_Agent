"""Metin sohbeti uç noktaları. Cevaplar Server-Sent Events (SSE) ile akar: sunucu tek bir
HTTP cevabı içinde cevabı parça parça (token token) gönderir."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser
from app.database import get_db
from app.schemas.chat import (
    ConversationCreate,
    ConversationOut,
    MessageOut,
    SendMessageRequest,
    SSEDelta,
    SSEDone,
    SSEEnvelope,
    SSEError,
    SSEMessageStart,
)
from app.services import persona_service
from app.services.chat_service import (
    ChatService,
    ConversationNotFoundError,
    Delta,
    Done,
    Error,
    MessageStart,
)

router = APIRouter(prefix="/chat", tags=["chat"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
chat_limit = Depends(rate_limited("chat", "rate_limit_chat_per_minute"))


def _service(request: Request) -> ChatService:
    service: ChatService = request.app.state.chat_service
    return service


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[default_limit],
)
async def create_conversation(
    request: Request, body: ConversationCreate, user: CurrentUser, db: DB
) -> ConversationOut:
    try:
        conversation = await _service(request).create_conversation(db, user, body.persona_id)
    except persona_service.PersonaNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Persona not found") from exc
    return ConversationOut.model_validate(conversation)


@router.get("/conversations", response_model=list[ConversationOut], dependencies=[default_limit])
async def list_conversations(request: Request, user: CurrentUser, db: DB) -> list[ConversationOut]:
    items = await _service(request).list_conversations(db, user)
    return [ConversationOut.model_validate(c) for c in items]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    dependencies=[default_limit],
)
async def get_conversation(
    request: Request, conversation_id: uuid.UUID, user: CurrentUser, db: DB
) -> ConversationOut:
    try:
        conversation = await _service(request).get_conversation(db, user, conversation_id)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    return ConversationOut.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
    dependencies=[default_limit],
)
async def list_messages(
    request: Request, conversation_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[MessageOut]:
    try:
        messages = await _service(request).list_messages(db, user, conversation_id)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    return [MessageOut.model_validate(m) for m in messages]


def _sse(event: str, payload: BaseModel) -> str:
    return f"event: {event}\ndata: {json.dumps(payload.model_dump(mode='json'))}\n\n"


@router.post(
    "/conversations/{conversation_id}/messages",
    dependencies=[chat_limit],
    responses={
        200: {
            "model": SSEEnvelope,
            "content": {
                "text/event-stream": {"schema": {"$ref": "#/components/schemas/SSEEnvelope"}}
            },
            "description": (
                "SSE stream. Events: message_start (SSEMessageStart), delta (SSEDelta), "
                "done (SSEDone), error (SSEError)."
            ),
        }
    },
)
async def send_message(
    request: Request,
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    user: CurrentUser,
    db: DB,
) -> StreamingResponse:
    service = _service(request)
    # Sahipliği akış başlamadan kontrol et; böylece 404 gerçek bir HTTP 404 olarak döner
    # (akış başladıktan sonra durum kodu artık değiştirilemez).
    try:
        await service.get_conversation(db, user, conversation_id)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for ev in service.stream_reply(
                db, user, conversation_id, body.content, body.idempotency_key
            ):
                if isinstance(ev, MessageStart):
                    yield _sse(
                        "message_start",
                        SSEMessageStart(
                            user_message_id=ev.user_message_id,
                            assistant_message_id=ev.assistant_message_id,
                        ),
                    )
                elif isinstance(ev, Delta):
                    yield _sse("delta", SSEDelta(text=ev.text))
                elif isinstance(ev, Done):
                    yield _sse(
                        "done",
                        SSEDone(
                            assistant_message_id=ev.assistant_message_id,
                            stop_reason=ev.stop_reason,
                            interrupted=ev.interrupted,
                        ),
                    )
                elif isinstance(ev, Error):
                    yield _sse("error", SSEError(code="provider_error", retryable=ev.retryable))
        except ConversationNotFoundError:
            yield _sse("error", SSEError(code="internal_error", retryable=False))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )
