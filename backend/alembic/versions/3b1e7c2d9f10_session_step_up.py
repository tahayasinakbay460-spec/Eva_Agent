"""oturuma adım-yukarı doğrulama zamanı

Revision ID: 3b1e7c2d9f10
Revises: 249b113fec82
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3b1e7c2d9f10"
down_revision: str | Sequence[str] | None = "249b113fec82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("step_up_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("step_up_at")
