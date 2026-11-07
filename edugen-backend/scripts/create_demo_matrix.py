"""Tạo ma trận demo ĐÃ XÁC NHẬN từ data/demo/matrix_toan12_demo.json, ghi thẳng vào DB.

API công khai chỉ tạo ma trận từ file ảnh/PDF tải lên (POST /matrices), không có đường tạo từ
JSON, nên script dùng đúng các hàm của app (kiểm ma trận như PUT /cells, rồi confirm) với
một session DB. Mật khẩu được kiểm để chắc đúng tài khoản GV.

    DEMO_PASSWORD='...' uv run python scripts/create_demo_matrix.py \n        --database-url postgresql+psycopg://... --email gv@nd.vn [--force]

Mật khẩu lấy từ biến môi trường DEMO_PASSWORD, không có thì hỏi bằng getpass (không đưa lên argv).
Đã có ma trận cùng tên của GV này thì in id và thoát, trừ khi có --force.
"""

import argparse
import getpass
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.v1.matrices import CellIn
from app.core.security import verify_password
from app.domain.matrix_reader import ParsedMatrix, check_totals
from app.models import ExamMatrix, User
from app.models.enums import MatrixStatus
from app.services.matrix_jobs import apply_parsed

DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "demo" / "matrix_toan12_demo.json"
NO_TOTALS_ROW = "Không thấy hàng"  # ma trận tạo từ JSON không có hàng tổng để đối chiếu


def load_fixture(path: Path) -> ParsedMatrix:
    data = json.loads(path.read_text(encoding="utf-8"))
    parsed = ParsedMatrix(
        subject=data["subject"], grade=data["grade"], name=data["name"],
        cells=[CellIn(**c).to_parsed() for c in data["cells"]],
    )  # fmt: skip
    parsed.issues += [i for i in check_totals(parsed) if not i.message.startswith(NO_TOTALS_ROW)]
    return parsed


def create_matrix(session: Session, user: User, parsed: ParsedMatrix) -> ExamMatrix:
    matrix_id = uuid.uuid4()
    matrix = ExamMatrix(
        id=matrix_id, school_id=user.school_id, owner_id=user.id,
        source_filename="matrix_toan12_demo.json", source_mime_type="application/json",
        source_storage_key=f"matrices/{matrix_id}/demo.json",
    )  # fmt: skip
    session.add(matrix)
    apply_parsed(session, matrix, parsed)
    if matrix.status is not MatrixStatus.parsed:
        raise SystemExit(f"Ma trận demo không hợp lệ: {matrix.parse_issues}")
    matrix.status, matrix.confirmed_at = MatrixStatus.confirmed, datetime.now(UTC)
    session.commit()
    return matrix


def find_existing(session: Session, user: User, name: str | None) -> ExamMatrix | None:
    return session.scalar(
        select(ExamMatrix).where(
            ExamMatrix.owner_id == user.id, ExamMatrix.school_id == user.school_id, ExamMatrix.name == name
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--force", action="store_true", help="tạo thêm dù đã có ma trận cùng tên")
    ap.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = ap.parse_args()
    parsed = load_fixture(args.fixture)
    if parsed.issues:
        sys.exit("Fixture không hợp lệ: " + "; ".join(i.message for i in parsed.issues))
    password = os.environ.get("DEMO_PASSWORD") or getpass.getpass("Mật khẩu: ")
    with Session(create_engine(args.database_url)) as session:
        user = session.scalar(select(User).where(User.email == args.email))
        if user is None or not verify_password(password, user.password_hash):
            sys.exit("Sai email hoặc mật khẩu")
        existing = None if args.force else find_existing(session, user, parsed.name)
        if existing:
            print(f"Đã có ma trận {existing.id} ({existing.name}), bỏ qua (dùng --force để tạo thêm)")
            return
        matrix = create_matrix(session, user, parsed)
        print(f"Đã tạo ma trận {matrix.id} ({matrix.name}), trạng thái {matrix.status.value}")


if __name__ == "__main__":
    main()
