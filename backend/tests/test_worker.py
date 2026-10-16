"""Arka plan kuyruğu ve işçisi (ADR 0003) ile anı vektörleri."""

import asyncio
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.database import utcnow
from app.models.job import Job
from app.models.memory import MemoryEmbedding
from app.worker import queue
from app.worker.jobs import EMBED_MEMORY
from app.worker.runner import WorkerContext, drain, handler, run_forever, run_once
from tests.conftest import build_app, make_settings


def _ctx(app: FastAPI) -> WorkerContext:
    ctx: WorkerContext = app.state.worker_context
    return ctx


async def _jobs(app: FastAPI, **filters: Any) -> list[Job]:
    async with app.state.session_factory() as db:
        query = select(Job)
        for key, value in filters.items():
            query = query.where(getattr(Job, key) == value)
        return list((await db.execute(query)).scalars().all())


async def _embedding(app: FastAPI, memory_id: str) -> MemoryEmbedding | None:
    async with app.state.session_factory() as db:
        embedding: MemoryEmbedding | None = await db.get(MemoryEmbedding, uuid.UUID(memory_id))
        return embedding


async def _add_memory(client: httpx.AsyncClient, headers: dict[str, str], text: str) -> str:
    r = await client.post("/memories", json={"content": text}, headers=headers)
    assert r.status_code == 201
    memory_id: str = r.json()["id"]
    return memory_id


# --- anı vektörleri ---------------------------------------------------------------


async def test_new_memory_is_embedded_in_the_background(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    memory_id = await _add_memory(client, auth_headers, "Kedimin adı Tarçın.")
    (job,) = await _jobs(app, kind=EMBED_MEMORY)
    assert job.status == "pending" and job.payload == {"memory_id": memory_id}
    assert await _embedding(app, memory_id) is None, "sohbet/istek vektörü beklemez"

    assert await drain(_ctx(app)) == 1
    embedding = await _embedding(app, memory_id)
    assert embedding is not None
    assert embedding.provider == "mock" and embedding.dimensions == len(embedding.vector) == 64
    assert [j.status for j in await _jobs(app)] == ["done"]


async def test_editing_text_re_embeds_but_other_edits_do_not(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    memory_id = await _add_memory(client, auth_headers, "Kedimin adı Tarçın.")
    await drain(_ctx(app))
    before = await _embedding(app, memory_id)

    await client.patch(
        f"/memories/{memory_id}", json={"sensitivity": "sensitive"}, headers=auth_headers
    )
    assert await _jobs(app, status="pending") == []

    await client.patch(
        f"/memories/{memory_id}", json={"content": "Kedimin adı Zeytin."}, headers=auth_headers
    )
    assert len(await _jobs(app, status="pending")) == 1
    await drain(_ctx(app))
    after = await _embedding(app, memory_id)
    assert before is not None and after is not None and before.vector != after.vector


async def test_forget_deletes_the_vector_too(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    memory_id = await _add_memory(client, auth_headers, "Eski sevgilim Can.")
    await drain(_ctx(app))
    assert await _embedding(app, memory_id) is not None
    await client.delete(f"/memories/{memory_id}", headers=auth_headers)
    async with app.state.session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(MemoryEmbedding))
    assert count == 0, "vektör de silinmeli (§6.5)"


async def test_embedding_a_memory_that_was_forgotten_meanwhile_is_a_no_op(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    memory_id = await _add_memory(client, auth_headers, "Geçici anı.")
    await client.delete(f"/memories/{memory_id}", headers=auth_headers)
    await drain(_ctx(app))
    assert [j.status for j in await _jobs(app)] == ["done"]
    assert await _embedding(app, memory_id) is None


# --- kuyruk davranışı -------------------------------------------------------------


@handler("test_always_fails")
async def _always_fails(_ctx: WorkerContext, _payload: dict[str, Any]) -> None:
    raise ConnectionError("sağlayıcıya ulaşılamadı: gizli içerik")


async def test_failed_job_is_retried_with_backoff_then_gives_up(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        await queue.enqueue(db, "test_always_fails", {}, max_attempts=2)
        await db.commit()

    assert await run_once(_ctx(app))
    (job,) = await _jobs(app)
    assert job.status == "pending" and job.attempts == 1
    assert job.run_at > utcnow() + timedelta(seconds=10), "hemen değil, bekleyip tekrar dener"
    assert job.last_error == "ConnectionError", "hata mesajı (içerik) değil, sadece türü"

    assert not await run_once(_ctx(app)), "zamanı gelmeden tekrar alınmaz"
    async with app.state.session_factory() as db:
        stored = await db.get(Job, job.id)
        assert stored is not None
        stored.run_at = utcnow()
        await db.commit()
    assert await run_once(_ctx(app))
    (job,) = await _jobs(app)
    assert job.status == "failed" and job.attempts == 2


async def test_unknown_job_kind_fails_instead_of_crashing(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        await queue.enqueue(db, "no_such_job", {}, max_attempts=1)
        await db.commit()
    assert await run_once(_ctx(app))
    (job,) = await _jobs(app)
    assert job.status == "failed" and job.last_error == "LookupError"


async def test_two_workers_never_take_the_same_job(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        await queue.enqueue(db, "anything", {})
        await db.commit()
    async with app.state.session_factory() as a, app.state.session_factory() as b:
        first, second = await asyncio.gather(queue.claim(a), queue.claim(b))
    assert [first is not None, second is not None].count(True) == 1


async def test_job_of_a_crashed_worker_returns_to_the_queue(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        await queue.enqueue(db, "anything", {})
        await db.commit()
        job = await queue.claim(db)
        assert job is not None
        stored = await db.get(Job, job.id)
        assert stored is not None
        stored.locked_at = utcnow() - queue.STALE_AFTER - timedelta(minutes=1)
        await db.commit()
    async with app.state.session_factory() as db:
        again = await queue.claim(db)
    assert again is not None and again.id == job.id and again.attempts == 2


async def test_dedupe_key_keeps_one_pending_job_and_moves_its_time(app: FastAPI) -> None:
    later = utcnow() + timedelta(minutes=10)
    async with app.state.session_factory() as db:
        await queue.enqueue(db, "extract", {"n": 1}, dedupe_key="conv-1", run_at=utcnow())
        await db.commit()
        await queue.enqueue(db, "extract", {"n": 2}, dedupe_key="conv-1", run_at=later)
        await db.commit()
    (job,) = await _jobs(app)
    assert job.payload == {"n": 2}
    assert abs((job.run_at - later).total_seconds()) < 1


async def test_run_forever_stops_when_asked(app: FastAPI) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(run_forever(_ctx(app), stop, poll_s=0.01))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=2)


async def test_in_process_worker_runs_inside_the_api(tmp_path: Path) -> None:
    app = await build_app(make_settings(tmp_path, worker_inprocess=True))
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
        ):
            r = await c.post("/auth/dev-login", json={"handle": "isci", "display_name": "İşçi"})
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
            memory_id = await _add_memory(c, headers, "Arka planda işlenecek anı.")
            for _ in range(100):
                if await _embedding(app, memory_id) is not None:
                    break
                await asyncio.sleep(0.05)
            assert await _embedding(app, memory_id) is not None
    finally:
        await app.state.engine.dispose()


@pytest.mark.parametrize("env, expected", [("dev", True), ("test", False), ("prod", False)])
def test_in_process_worker_default(tmp_path: Path, env: str, expected: bool) -> None:
    assert make_settings(tmp_path, env=env).run_worker_inprocess is expected
