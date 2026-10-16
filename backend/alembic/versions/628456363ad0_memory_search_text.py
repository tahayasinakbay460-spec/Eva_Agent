"""memory search text

Revision ID: 628456363ad0
Revises: ceeee9ca314d
Create Date: 2026-10-16 13:30:00.000000

Anılara aramaya hazır, küçük harfli bir metin sütunu ekler ve var olan anılar için
doldurur. Dönüşüm burada kopyalanmıştır: migration'lar uygulama kodu değişse de
aynı sonucu vermeli.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Alembic'in migration sırasını izlediği kimlikler (elle değiştirilmez).
revision: str = "628456363ad0"
down_revision: str | Sequence[str] | None = "ceeee9ca314d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _search_text(content: str, people: object) -> str:
    if isinstance(people, str):
        people = json.loads(people)
    names = [str(p) for p in people] if isinstance(people, list) else []
    text = " ".join([content, *names])
    return text.replace("I", "ı").replace("İ", "i").lower()


def upgrade() -> None:
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.add_column(sa.Column("search_text", sa.Text(), nullable=False, server_default=""))

    bind = op.get_bind()
    memories = sa.table(
        "memories",
        sa.column("id", sa.Uuid()),
        sa.column("content", sa.Text()),
        sa.column("people", sa.JSON()),
        sa.column("search_text", sa.Text()),
    )
    rows = bind.execute(sa.select(memories.c.id, memories.c.content, memories.c.people)).all()
    for row in rows:
        bind.execute(
            memories.update()
            .where(memories.c.id == row.id)
            .values(search_text=_search_text(row.content, row.people))
        )


def downgrade() -> None:
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.drop_column("search_text")
