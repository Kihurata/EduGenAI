"""exam_kind of sample exam drafts follows D-017

Tóm tắt: bản nháp đề mẫu (T-050) lưu loại đề theo bộ cũ `dinh_ky | thi_thu | khac`; D-017 mục 5 chốt một bộ
`tot_nghiep | dinh_ky_7991` dùng chung với chỉ mục và ma trận. Migration đổi `draft.exam_kind` của các bản ghi cũ
bằng `migrate_exam_kind` (T-055, TC-028). Downgrade không đổi lại: bộ cũ không còn được kiểm tra nhận.

Revision ID: 0004
Revises: 0003
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.domain.exam_draft import migrate_exam_kind

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, grade, draft FROM sample_exams WHERE draft IS NOT NULL")).all()
    for row_id, grade, draft in rows:
        draft = json.loads(draft) if isinstance(draft, str) else draft  # SQLite trả chuỗi JSON
        if not isinstance(draft, dict):
            continue
        new = migrate_exam_kind(draft.get("exam_kind"), grade)
        if new == draft.get("exam_kind"):
            continue
        draft["exam_kind"] = new
        value = json.dumps(draft, ensure_ascii=False)
        cast = "CAST(:draft AS JSONB)" if bind.dialect.name == "postgresql" else ":draft"
        bind.execute(sa.text(f"UPDATE sample_exams SET draft = {cast} WHERE id = :id"), {"draft": value, "id": row_id})


def downgrade() -> None:
    pass
