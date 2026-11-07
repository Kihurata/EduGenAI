"""sample exam review draft

Đề mẫu (T-050): bản nháp JSON GV duyệt trước khi nạp RAG (`draft`, `draft_issues`) và trạng thái
`needs_review` của IngestStatus (dùng chung cho đề mẫu và ngân hàng đề). Postgres: thêm giá trị vào hai
enum; SQLite lưu enum thành VARCHAR theo giá trị dài nhất nên phải nới cột. DB dựng bằng `create_all`
rồi stamp có sẵn cột mới, nên chỉ thêm cột còn thiếu.

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ("pending", "sent", "ingested", "failed")
NEW = ("pending", "needs_review", "sent", "ingested", "failed")
STATUS_COLUMNS = (("sample_exams", "status", "sample_exam_status"), ("exam_bank_entries", "rag_status", "bank_ingest_status"))
DRAFT_COLUMNS = ("draft", "draft_issues")


def _set_status_values(values: tuple[str, ...], previous: tuple[str, ...]) -> None:
    for table, column, enum_name in STATUS_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=sa.Enum(*values, name=enum_name),
                               existing_type=sa.Enum(*previous, name=enum_name), existing_nullable=False)


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Postgres 12+ runs ADD VALUE inside a transaction as long as the new value isn't used in it; no
        # autocommit block, which breaks when the caller (tests, app startup) already holds a transaction.
        for _, _, enum_name in STATUS_COLUMNS:
            op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS 'needs_review' AFTER 'pending'")
        for name in DRAFT_COLUMNS:  # IF NOT EXISTS: no inspector needed, so `alembic upgrade --sql` works too
            op.execute(f"ALTER TABLE sample_exams ADD COLUMN IF NOT EXISTS {name} JSONB")
        return
    _set_status_values(NEW, OLD)
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sample_exams")}
    for name in DRAFT_COLUMNS:
        if name not in existing:
            op.add_column("sample_exams", sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Postgres cannot drop an enum value: rows in needs_review go back to pending, the value stays.
    # Compare as text: a 'needs_review' enum literal fails if the value was added in this same transaction.
    op.execute("UPDATE sample_exams SET status = 'pending' WHERE CAST(status AS TEXT) = 'needs_review'")
    op.execute("UPDATE exam_bank_entries SET rag_status = 'pending' WHERE CAST(rag_status AS TEXT) = 'needs_review'")
    for name in DRAFT_COLUMNS:
        op.drop_column("sample_exams", name)
    if op.get_bind().dialect.name != "postgresql":
        _set_status_values(OLD, NEW)
