"""Chạy BE để thử frontend trên máy, không cần Postgres, dịch vụ RAG hay marker.

    uv run python scripts/dev_server.py            # http://localhost:8000, /docs
    uv run python scripts/dev_server.py --reset    # xoá DB + file đã lưu, seed lại

- DB: SQLite file `dev_data/edugen.db` (JSONB chạy như JSON, giống test). Bảng tạo bằng create_all.
- Tài khoản seed sẵn: admin@nd.vn (admin), gv@nd.vn (giáo viên). Mật khẩu lấy từ biến môi trường
  `EDUGEN_DEV_PASSWORD` lúc seed, không đặt thì sinh ngẫu nhiên; lưu ở `dev_data/password.txt` và in ra
  mỗi lần chạy.
- RAG: giả lập từ `tests/fixtures/rag/ket_qua_mau.json` và `ket_qua_mau_hinh.json` (câu mẫu lặp lại, không phải câu sinh
  thật; file hình có hình hộp, chóp, lăng trụ để thử luồng vẽ hình). Không cần khoá LLM hay Qdrant.
- Ma trận: có `marker_single` thì chạy marker thật; không thì ảnh tải lên phải trùng (theo nội dung)
  một ảnh trong `--matrix-dir`, và BE đọc file `.md` cùng tên cạnh ảnh đó. Thêm đề mẫu = thêm cặp
  `ten.png` + `ten.md` (markdown marker đã xuất) vào thư mục này.
"""

import argparse
import hashlib
import os
import secrets
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # đăng ký mọi bảng cho create_all
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session_factory
from app.main import app
from app.models import User
from app.models.enums import UserRole
from app.seed import seed
from app.services.matrix_converter import (
    ConversionError,
    MarkerConverter,
    get_matrix_converter,
)
from app.services.rag_client import get_rag_client
from app.services.rag_mock import SampleRag
from app.services.storage import LocalStorage, get_storage

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND / "tests" / "fixtures"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf"}


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


class PresetConverter:
    """Ảnh ma trận → markdown đã chuẩn bị sẵn, so khớp theo SHA-256 nội dung ảnh."""

    def __init__(self, folder: Path) -> None:
        self.markdown = {
            hashlib.sha256(img.read_bytes()).hexdigest(): img.with_suffix(".md")
            for img in sorted(folder.iterdir())
            if img.suffix.lower() in IMAGE_SUFFIXES and img.with_suffix(".md").exists()
        }

    def convert(self, source: Path) -> str:
        md = self.markdown.get(hashlib.sha256(source.read_bytes()).hexdigest())
        if md is None:
            raise ConversionError("Máy dev chưa cài marker: chỉ nhận ảnh ma trận mẫu trong thư mục dev")
        return md.read_text(encoding="utf-8")


def make_factory(db_path: Path) -> sessionmaker:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def demo_password(data_dir: Path) -> str:
    """Mật khẩu hai tài khoản demo; chọn một lần khi tạo DB rồi giữ nguyên tới khi `--reset`."""
    saved = data_dir / "password.txt"
    if not saved.exists():
        saved.write_text(os.environ.get("EDUGEN_DEV_PASSWORD") or secrets.token_urlsafe(9), encoding="utf-8")
    return saved.read_text(encoding="utf-8").strip()


def seed_demo(factory: sessionmaker, password: str) -> None:
    with factory() as session:
        if session.scalar(select(User).where(User.email == "admin@nd.vn")):
            return
        school, _ = seed(session, "nd", "THPT Nguyễn Du", "admin@nd.vn", password, "Quản trị ND")
        session.add(User(
            school_id=school.id, email="gv@nd.vn", password_hash=hash_password(password),
            full_name="Giáo viên Toán", role=UserRole.teacher,
        ))  # fmt: skip
        session.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="BE dev cho frontend: SQLite + RAG giả lập")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data-dir", type=Path, default=BACKEND / "dev_data")
    ap.add_argument("--matrix-dir", type=Path, default=FIXTURES / "matrices")
    ap.add_argument("--samples", type=Path, nargs="+", default=[FIXTURES / "rag" / "ket_qua_mau.json", FIXTURES / "rag" / "ket_qua_mau_hinh.json"])
    ap.add_argument("--reset", action="store_true", help="xoá DB và file đã lưu trước khi chạy")
    args = ap.parse_args()

    data_dir = args.data_dir.resolve()
    if args.reset and data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    factory = make_factory(data_dir / "edugen.db")
    password = demo_password(data_dir)
    seed_demo(factory, password)
    storage = LocalStorage(data_dir / "storage")
    rag = SampleRag.from_files(*args.samples)
    if shutil.which("marker_single"):
        converter = MarkerConverter(settings.marker_config_path, timeout=settings.marker_timeout_seconds)
    else:
        converter = PresetConverter(args.matrix_dir.resolve())
        print(f"marker chưa cài → dùng {len(converter.markdown)} ma trận mẫu trong {args.matrix_dir}")

    app.dependency_overrides.update({
        get_session_factory: lambda: factory,
        get_storage: lambda: storage,
        get_matrix_converter: lambda: converter,
        get_rag_client: lambda: rag,
    })  # fmt: skip
    print(f"Tài khoản: admin@nd.vn / gv@nd.vn, mật khẩu {password}")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
