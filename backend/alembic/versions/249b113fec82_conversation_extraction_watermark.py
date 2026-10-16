"""conversation extraction watermark

Revision ID: 249b113fec82
Revises: 9a2e5ca5b74c
Create Date: 2026-10-16 15:00:00.000000

Sohbetlere "bu tarihe kadarki mesajlardan anı çıkarıldı" işareti ekler.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Alembic'in migration sırasını izlediği kimlikler (elle değiştirilmez).
revision: str = "249b113fec82"
down_revision: str | Sequence[str] | None = "9a2e5ca5b74c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("memories_extracted_until", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_column("memories_extracted_until")
