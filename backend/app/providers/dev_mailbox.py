"""Yalnızca geliştirme için mesaj adaptörü: her e-posta/SMS'i bir metin dosyasına yazar.

E-posta sağlayıcısı seçilene kadar (§15) lokal kayıt ve giriş kodları
``backend/dev_mailbox/`` klasörüne düşer (git'e girmez); böylece mail sunucusu olmadan
okunabilir. ``create_app`` bu adaptörü dev/test dışında kabul etmez.
"""

import asyncio
import itertools
import os
from datetime import UTC, datetime
from pathlib import Path

from app.providers.base import MessageReceipt, OutboundMessage
from app.providers.message_templates import render

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "dev_mailbox"


class DevMailboxMessagingProvider:
    name = "dev_mailbox"

    def __init__(self, directory: Path | None = None) -> None:
        env_dir = os.environ.get("EVA_DEV_MAILBOX_DIR")
        self._dir = directory or (Path(env_dir) if env_dir else _DEFAULT_DIR)
        self._ids = itertools.count(1)

    async def send(self, message: OutboundMessage) -> MessageReceipt:
        if not message.to:
            raise ValueError("recipient is required")
        rendered = render(message)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        message_id = f"dev-{stamp}-{next(self._ids)}"
        text = (
            f"To: {message.to}\nChannel: {message.channel}\nSubject: {rendered.subject}\n\n"
            f"{rendered.body}\n"
        )
        await asyncio.to_thread(self._write, f"{message_id}.txt", text)
        return MessageReceipt(provider=self.name, message_id=message_id)

    def _write(self, filename: str, text: str) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / filename).write_text(text, encoding="utf-8")
