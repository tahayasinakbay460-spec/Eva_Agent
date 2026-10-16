"""İşçiyi ayrı bir süreç olarak çalıştırır:  uv run python -m app.worker

Ctrl+C ile durur; elindeki işi bitirip çıkar.
"""

import asyncio
import contextlib
import logging
import signal

from app.core.config import get_settings
from app.core.telemetry import setup_telemetry
from app.database import create_engine, create_session_factory
from app.providers.registry import build_registry
from app.worker import handlers  # noqa: F401 - işleyicileri kaydeder
from app.worker.runner import WorkerContext, run_forever


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO if settings.is_dev else logging.WARNING)
    setup_telemetry(settings)
    engine = create_engine(settings.database_url)
    ctx = WorkerContext(
        session_factory=create_session_factory(engine),
        registry=build_registry(settings),
        settings=settings,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Windows'ta sinyal işleyici eklenemez; orada Ctrl+C KeyboardInterrupt olarak gelir.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    try:
        await run_forever(ctx, stop)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
