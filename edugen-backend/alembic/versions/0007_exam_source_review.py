"""exam source and bank review

GV chọn nguồn dữ liệu sinh đề (`exams.source`: school | personal). Đề nguồn trường duyệt xong vào hàng chờ admin
xét chọn làm đề chính thức (`review_status`: pending | accepted | rejected, `review_note` = lý do không chọn); đề
cá nhân ở lại bộ sưu tập của GV. Đề cũ coi là nguồn trường: đề đã duyệt đang ở ngân hàng → accepted, còn lại → pending.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = {
    "source": sa.Column("source", sa.String(length=16), nullable=False, server_default="school"),
    "review_status": sa.Column("review_status", sa.String(length=16), nullable=True),
    "review_note": sa.Column("review_note", sa.Text(), nullable=True),
}


def upgrade() -> None:
    bind = op.get_bind()
    # A DB built with create_all and then stamped already has the columns.
    existing = {c["name"] for c in sa.inspect(bind).get_columns("exams")}
    for name, column in COLUMNS.items():
        if name not in existing:
            op.add_column("exams", column)
    bind.execute(sa.text(
        "UPDATE exams SET review_status = CASE WHEN EXISTS "
        "(SELECT 1 FROM exam_bank_entries b WHERE b.exam_id = exams.id) THEN 'accepted' ELSE 'pending' END "
        "WHERE status = 'approved' AND source = 'school' AND review_status IS NULL"
    ))


def downgrade() -> None:
    with op.batch_alter_table("exams") as batch:
        for name in reversed(list(COLUMNS)):
            batch.drop_column(name)
