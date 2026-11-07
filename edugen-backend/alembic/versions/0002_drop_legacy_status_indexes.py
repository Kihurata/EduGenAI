"""drop legacy status indexes

DB dựng bằng `create_all` trước khi có Alembic còn các index trên cột `status`
(không truy vấn nào lọc theo status). Sau `alembic stamp 0001`, revision này gỡ chúng.
Trên DB mới (đi từ 0001) các index không tồn tại nên không làm gì.

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY = (
    ("exams", "ix_exams_status"),
    ("exam_matrices", "ix_exam_matrices_status"),
    ("sample_exams", "ix_sample_exams_status"),
)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, name in LEGACY:
        if name in {ix["name"] for ix in insp.get_indexes(table)}:
            op.drop_index(name, table_name=table)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, name in LEGACY:
        if name not in {ix["name"] for ix in insp.get_indexes(table)}:
            op.create_index(name, table, ["status"], unique=False)
