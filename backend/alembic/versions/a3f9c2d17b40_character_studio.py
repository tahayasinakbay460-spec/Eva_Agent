"""karakter stüdyosu: görünürlük, karakterin yüz görseli ve varsayılan sesi

Revision ID: a3f9c2d17b40
Revises: e7a1c4d2b9f0
Create Date: 2026-10-19 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c2d17b40"
down_revision: str | Sequence[str] | None = "e7a1c4d2b9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("personas", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("visibility", sa.String(length=16), server_default="private", nullable=False)
        )
        batch_op.add_column(sa.Column("face_blob_key", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("face_media_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("voice_key", sa.String(length=32), nullable=True))
        batch_op.create_index("ix_personas_visibility", ["visibility"])


def downgrade() -> None:
    with op.batch_alter_table("personas", schema=None) as batch_op:
        batch_op.drop_index("ix_personas_visibility")
        batch_op.drop_column("voice_key")
        batch_op.drop_column("face_media_type")
        batch_op.drop_column("face_blob_key")
        batch_op.drop_column("visibility")
