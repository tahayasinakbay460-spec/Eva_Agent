"""email password auth

Revision ID: 94eea96a255b
Revises: c73b780715fc
Create Date: 2026-10-16 12:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Alembic'in migration sırasını izlediği kimlikler (elle değiştirilmez).
revision: str = "94eea96a255b"
down_revision: str | Sequence[str] | None = "c73b780715fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_codes",
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("auth_codes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_auth_codes_email"), ["email"], unique=False)
        batch_op.create_index(batch_op.f("ix_auth_codes_expires_at"), ["expires_at"], unique=False)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch_op.add_column(
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("uq_users_email", ["email"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("password_hash")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email")

    with op.batch_alter_table("auth_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_auth_codes_expires_at"))
        batch_op.drop_index(batch_op.f("ix_auth_codes_email"))
    op.drop_table("auth_codes")
