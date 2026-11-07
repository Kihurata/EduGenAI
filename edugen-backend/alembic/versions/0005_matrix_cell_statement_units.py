"""matrix cell statement units

Ô Đúng–Sai lưu thêm đơn vị kiến thức của từng ý a–d (`statement_units`, JSONB, null = không rõ): một câu
trên ma trận có thể rải ý qua nhiều đơn vị, khi đó content_unit null nhưng từng ý vẫn biết thuộc đơn vị nào.

Revision ID: 0005
Revises: 0004
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # IF NOT EXISTS: a DB built with create_all and then stamped already has the column
        op.execute("ALTER TABLE matrix_cells ADD COLUMN IF NOT EXISTS statement_units JSONB")
        return
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("matrix_cells")}
    if "statement_units" not in existing:
        op.add_column("matrix_cells", sa.Column("statement_units", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("matrix_cells") as batch:
        batch.drop_column("statement_units")
