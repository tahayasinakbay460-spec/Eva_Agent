"""memories

Revision ID: ceeee9ca314d
Revises: 94eea96a255b
Create Date: 2026-10-16 10:50:29.819918

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# Alembic'in migration sırasını izlediği kimlikler (elle değiştirilmez).
revision: str = "ceeee9ca314d"
down_revision: str | Sequence[str] | None = "94eea96a255b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column(
            "people",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("emotion", sa.String(length=32), nullable=True),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("sensitivity", sa.String(length=16), nullable=False),
        sa.Column("legacy_scope", sa.String(length=16), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.create_index("ix_memories_user_persona", ["user_id", "persona_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.drop_index("ix_memories_user_persona")
    op.drop_table("memories")
