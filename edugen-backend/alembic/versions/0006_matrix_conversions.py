"""matrix conversions cache

Cache JSON Gemini đọc từ file ma trận (`matrix_conversions`): khoá (source_sha256, cache_key), dùng chung mọi trường.
DB dựng bằng `create_all` rồi stamp có sẵn bảng, nên chỉ tạo khi còn thiếu.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "matrix_conversions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "matrix_conversions",
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matrix_conversions")),
        sa.UniqueConstraint("source_sha256", "cache_key", name=op.f("uq_matrix_conversions_source_sha256")),
    )


def downgrade() -> None:
    op.drop_table("matrix_conversions")
