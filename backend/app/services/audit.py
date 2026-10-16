"""Denetim kaydı (``audit_log``) yazmak için tek giriş noktası. Commit çağıranın işi: kayıt,
onu doğuran değişiklikle aynı commit'te yazılır (biri olup diğeri kaybolmasın)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.biometric import AuditLog


def record(
    db: AsyncSession,
    *,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    meta: dict[str, Any] | None = None,
) -> None:
    """``meta``'ya yalnızca kodlar ve id'ler konur; içerik ya da kişisel veri asla (§2.6)."""
    db.add(
        AuditLog(
            action=action,
            target_type=target_type,
            target_id=target_id,
            user_id=user_id,
            actor_id=actor_id,
            meta=meta or {},
        )
    )
