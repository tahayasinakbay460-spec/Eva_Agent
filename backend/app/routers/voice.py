"""Sesli/görüntülü görüşme uç noktaları (Faz 2). Sesin kendisi buradan geçmez: tarayıcı
LiveKit odasına bağlanır, EVA'nın ajanı (``realtime/``) aynı odaya katılır."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser
from app.database import get_db
from app.schemas.voice import (
    CallCreate,
    CallOut,
    CallStatusOut,
    LatencyReportOut,
    StageSummaryOut,
    TurnLatencyOut,
)
from app.services import persona_service, voice_service

router = APIRouter(prefix="/voice", tags=["voice"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
call_limit = Depends(rate_limited("call", "rate_limit_call_per_minute"))

# CLAUDE.md §4.4 başlangıç hedefleri (milisaniye).
LATENCY_TARGETS = {
    "e2e_ms": {"p50": 800.0, "p95": 1500.0},
    "avatar_first_frame_ms": {"p50": 1500.0, "p95": 2500.0},
}


@router.post(
    "/calls",
    response_model=CallOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[call_limit],
    responses={503: {"description": "voice_not_configured"}, 429: {"description": "quota"}},
)
async def start_call(request: Request, body: CallCreate, user: CurrentUser, db: DB) -> CallOut:
    try:
        started = await voice_service.start_call(
            db, request.app.state.settings, user, persona_id=body.persona_id, mode=body.mode
        )
    except voice_service.VoiceNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "voice_not_configured") from exc
    except voice_service.VideoQuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "video_quota_exceeded") from exc
    except persona_service.PersonaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Persona not found") from exc
    call = started.call
    return CallOut(
        call_id=call.id,
        conversation_id=call.conversation_id,
        mode=body.mode,
        livekit_url=started.url,
        token=started.token,
        max_duration_s=call.max_duration_s,
        idle_timeout_s=call.idle_timeout_s,
    )


@router.get("/calls/{call_id}", response_model=CallStatusOut, dependencies=[default_limit])
async def get_call(call_id: uuid.UUID, user: CurrentUser, db: DB) -> CallStatusOut:
    try:
        call = await voice_service.get_call(db, user, call_id)
    except voice_service.CallNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found") from exc
    return CallStatusOut.model_validate(call)


@router.post(
    "/calls/{call_id}/end",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[default_limit],
)
async def end_call(call_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    try:
        call = await voice_service.get_call(db, user, call_id)
    except voice_service.CallNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found") from exc
    await voice_service.end_call(db, call, "user")


@router.get("/latency", response_model=LatencyReportOut, dependencies=[default_limit])
async def latency_report(user: CurrentUser, db: DB) -> LatencyReportOut:
    turns = await voice_service.recent_turns(db, user.id)
    summary = voice_service.summarize(turns)
    return LatencyReportOut(
        stages={
            k: StageSummaryOut(p50=v.p50, p95=v.p95, count=v.count) for k, v in summary.items()
        },
        turns=[TurnLatencyOut.model_validate(t) for t in turns[:20]],
        targets_ms=LATENCY_TARGETS,
    )
