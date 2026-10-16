"""passkeys and auth challenges

Revision ID: c73b780715fc
Revises: 817cab0c9a74
Create Date: 2026-10-16 09:43:05.694489

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Alembic'in migration sırasını izlediği kimlikler (elle değiştirilmez).
revision: str = "c73b780715fc"
down_revision: str | Sequence[str] | None = "817cab0c9a74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_challenges",
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("challenge", sa.LargeBinary(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("auth_challenges", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_auth_challenges_expires_at"), ["expires_at"], unique=False
        )

    op.create_table(
        "passkeys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(length=1024), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("transports", sa.JSON(), nullable=False),
        sa.Column("aaguid", sa.String(length=36), nullable=False),
        sa.Column("backed_up", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id", name="uq_passkeys_credential_id"),
    )
    with op.batch_alter_table("passkeys", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_passkeys_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("webauthn_user_id", sa.LargeBinary(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("age_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("ai_disclosure_accepted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_unique_constraint("uq_users_webauthn_user_id", ["webauthn_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_webauthn_user_id", type_="unique")
        batch_op.drop_column("ai_disclosure_accepted_at")
        batch_op.drop_column("age_confirmed_at")
        batch_op.drop_column("webauthn_user_id")

    with op.batch_alter_table("passkeys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_passkeys_user_id"))
    op.drop_table("passkeys")

    with op.batch_alter_table("auth_challenges", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_auth_challenges_expires_at"))
    op.drop_table("auth_challenges")
