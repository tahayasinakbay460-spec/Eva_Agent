"""ses ve yüz seçimi: kullanıcı tercihleri, görüşmede seçilen ses/yüz anahtarı

Revision ID: e7a1c4d2b9f0
Revises: 6b62bc21564a
Create Date: 2026-10-17 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a1c4d2b9f0"
down_revision: str | Sequence[str] | None = "6b62bc21564a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.Uuid(), nullable=False),
        sa.Column("voice_key", sa.String(length=32), nullable=True),
        sa.Column("avatar_key", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "persona_id"),
    )
    with op.batch_alter_table("call_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("voice_key", sa.String(length=32), server_default="eva", nullable=False)
        )
        batch_op.add_column(sa.Column("avatar_key", sa.String(length=32), nullable=True))
    # Eski kayıtlar: "self" = kullanıcının kendi klonu, değilse EVA'nın kendi sesi/yüzü.
    op.execute(
        "UPDATE call_sessions SET "
        "voice_key = CASE WHEN media_source = 'self' THEN 'own' ELSE 'eva' END, "
        "avatar_key = CASE WHEN mode = 'video' THEN "
        "(CASE WHEN media_source = 'self' THEN 'own' ELSE 'eva' END) ELSE NULL END"
    )
    with op.batch_alter_table("call_sessions", schema=None) as batch_op:
        batch_op.drop_column("media_source")


def downgrade() -> None:
    with op.batch_alter_table("call_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("media_source", sa.String(length=8), server_default="persona", nullable=False)
        )
    op.execute(
        "UPDATE call_sessions SET media_source = "
        "CASE WHEN voice_key = 'own' THEN 'self' ELSE 'persona' END"
    )
    with op.batch_alter_table("call_sessions", schema=None) as batch_op:
        batch_op.drop_column("avatar_key")
        batch_op.drop_column("voice_key")
    op.drop_table("media_preferences")
