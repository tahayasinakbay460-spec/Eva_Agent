"""Sohbet sırasında ilgili anıları bulma (CLAUDE.md §6.3).

Her mesajda çalışır, yani "sıcak yol"dadır: cevabı geciktirmemesi için tek bir
veritabanı sorgusu atar ve puanlamayı bellekte yapar (hedef: 20 ms altı, §4.4).

Puan (her biri 0 ile 1 arası) dört parçadan oluşur:
- kelime eşleşmesi: mesajdaki kelimeler anıda geçiyor mu? Türkçe ekler için kelimelerin
  ilk 5 harfi karşılaştırılır ("Bodrum'a" ile "Bodrum" eşleşir).
- anlam benzerliği: embedding vektörleri. Embedding sağlayıcısı seçilene kadar (§15)
  sıfır sayılır; adım 3'te bağlanacak.
- yakınlık: yeni anılar biraz öne çıkar.
- önem: önemli anılar biraz öne çıkar.

Ayrıca en önemli birkaç kalıcı bilgi ("kahveyi sütsüz içer") konu açılmasa da her zaman
eklenir; EVA'nın seni tanıdığı hissi buradan gelir.
"""

import math
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telemetry import record_memory_retrieval
from app.database import utcnow
from app.models.memory import Memory, turkish_lower

# Kaç anı adayı okunacak. Kullanıcı başına sınır 5000; en yeni 2000 tanesi fazlasıyla yeter.
CANDIDATE_LIMIT = 2000
# Mesajla ilgili olarak eklenecek en fazla anı sayısı.
TOP_K = 6
# Konu açılmasa da her zaman eklenecek en önemli kalıcı bilgi sayısı.
CORE_FACTS = 3
# Yakınlık puanı bu kadar günde yarıya iner.
RECENCY_HALF_LIFE_DAYS = 30.0

W_KEYWORD, W_SEMANTIC, W_RECENCY, W_IMPORTANCE = 0.6, 0.25, 0.05, 0.10

# Anlamı az, her cümlede geçen kelimeler: eşleşme sayılmaz.
_STOPWORDS = frozenset(
    "ve ile ama fakat ki de da mi mı mu mü bir bu şu o ben sen biz siz onlar çok daha "
    "gibi için diye ne neden nasıl nerede şey var yok evet hayır şimdi sonra önce bana "
    "sana beni seni benim senin olan oldu olarak ise hem en the and you are was".split()
)
_WORD = re.compile(r"[0-9a-zçğıöşü]+")
STEM_LEN = 5


@dataclass(frozen=True, slots=True)
class Candidate:
    """Puanlama için gereken alanlar. Tam ORM nesnesi yüklemek 2000 anıda çok yavaş."""

    id: object
    kind: str
    content: str
    people: list[str]
    importance: float
    created_at: datetime
    occurred_on: date | None


def _stems(text: str) -> set[str]:
    words = _WORD.findall(turkish_lower(text))
    return {w[:STEM_LEN] for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _keyword_score(query: set[str], memory: set[str]) -> float:
    if not query or not memory:
        return 0.0
    return len(query & memory) / len(query)


def _recency_score(created_at: datetime, now: datetime) -> float:
    age_days = max((now - created_at).total_seconds() / 86_400, 0.0)
    return math.exp(-math.log(2) * age_days / RECENCY_HALF_LIFE_DAYS)


def _format_date(d: date) -> str:
    return d.isoformat()


def render_memory(memory: Candidate | Memory) -> str:
    """Prompt'a girecek tek satır: "[anı · 2025-07-20 · annem] Bodrum'a gittik"."""
    tags = ["anı" if memory.kind == "episode" else "bilgi"]
    if memory.occurred_on is not None:
        tags.append(_format_date(memory.occurred_on))
    if memory.people:
        tags.append(", ".join(memory.people))
    return f"[{' · '.join(tags)}] {memory.content}"


def rank[M: (Candidate, Memory)](
    memories: Sequence[M], query_text: str, *, now: datetime, top_k: int, core_facts: int
) -> list[M]:
    """Saf fonksiyon (veritabanı yok): test etmesi ve ölçmesi kolay."""
    query = _stems(query_text)
    scored: list[tuple[float, M]] = []
    for m in memories:
        keyword = _keyword_score(query, _stems(m.content + " " + " ".join(m.people)))
        if keyword == 0.0:
            continue  # konuyla ilgisi yok; kalıcı bilgiler aşağıda ayrıca ele alınıyor
        score = (
            W_KEYWORD * keyword
            + W_RECENCY * _recency_score(m.created_at, now)
            + W_IMPORTANCE * m.importance
        )
        scored.append((score, m))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    picked = [m for _, m in scored[:top_k]]

    chosen = {m.id for m in picked}
    facts = sorted(
        (m for m in memories if m.kind == "fact" and m.id not in chosen),
        key=lambda m: m.importance,
        reverse=True,
    )
    return picked + facts[:core_facts]


def _columns() -> tuple[Any, ...]:
    return (
        Memory.id,
        Memory.kind,
        Memory.content,
        Memory.people,
        Memory.importance,
        Memory.created_at,
        Memory.occurred_on,
    )


async def retrieve(
    db: AsyncSession, *, user_id: object, persona_id: object, query_text: str
) -> list[str]:
    """Mesaja göre prompt'a eklenecek anı satırlarını döndürür. Süresi ölçülür.

    Tek sorgu, iki parça (UNION ALL):
    1. arama metninde mesajdaki kelime köklerinden biri geçen anılar,
    2. en önemli kalıcı bilgiler.
    Böylece 2000 anının hepsi değil, sadece işe yarayabilecekler okunur.
    """
    started = time.perf_counter()
    owned = (Memory.user_id == user_id, Memory.persona_id == persona_id)
    facts = (
        select(*_columns())
        .where(*owned, Memory.kind == "fact")
        .order_by(Memory.importance.desc())
        .limit(CORE_FACTS + TOP_K)
        .subquery()
    )
    query: Any = select(facts)
    stems = sorted(_stems(query_text))
    if stems:
        # Kökler sadece harf/rakam içerir (regex), yani LIKE'ın % ve _ işaretleri giremez.
        matches = (
            select(*_columns())
            .where(*owned, or_(*(Memory.search_text.like(f"%{stem}%") for stem in stems)))
            .order_by(Memory.created_at.desc())
            .limit(CANDIDATE_LIMIT)
            .subquery()
        )
        query = union_all(select(matches), select(facts))
    rows = (await db.execute(query)).all()

    seen: set[object] = set()
    memories: list[Candidate] = []
    for row in rows:
        if row[0] not in seen:
            seen.add(row[0])
            memories.append(Candidate(*row))
    picked = rank(memories, query_text, now=utcnow(), top_k=TOP_K, core_facts=CORE_FACTS)
    record_memory_retrieval((time.perf_counter() - started) * 1000, candidates=len(memories))
    return [render_memory(m) for m in picked]
