"""jobs and memory embeddings

Revision ID: 9a2e5ca5b74c
Revises: 628456363ad0
Create Date: 2026-10-16 14:20:00.000000

İş kuyruğu tablosu (ADR 0003) ve anı vektörleri. Vektör sütunu Postgres'te pgvector'ün
``vector`` tipidir (eklenti burada açılır), SQLite'ta JSON listedir.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

from alembic import op

# Alembic'in migration sırasını izlediği kimlikler (elle değiştirilmez).
revision: str = "9a2e5ca5b74c"
down_revision: str | Sequence[str] | None = "628456363ad0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PENDING_WITH_KEY = "status = 'pending' AND dedupe_key IS NOT NULL"


def upgrade() -> None:
    is_postgres = op.get_bind().dialect.name == "postgresql"

    op.create_table(
        "jobs",
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_index("ix_jobs_status_run_at", ["status", "run_at"], unique=False)
        batch_op.create_index(
            "uq_jobs_pending_dedupe",
            ["dedupe_key"],
            unique=True,
            sqlite_where=sa.text(_PENDING_WITH_KEY),
            postgresql_where=sa.text(_PENDING_WITH_KEY),
        )

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "memory_embeddings",
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", VECTOR() if is_postgres else sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("memory_id"),
    )


def downgrade() -> None:
    op.drop_table("memory_embeddings")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_jobs_pending_dedupe",
            sqlite_where=sa.text(_PENDING_WITH_KEY),
            postgresql_where=sa.text(_PENDING_WITH_KEY),
        )
        batch_op.drop_index("ix_jobs_status_run_at")
    op.drop_table("jobs")
    # vector eklentisi bilerek bırakılır: başka tablolar da kullanıyor olabilir.
