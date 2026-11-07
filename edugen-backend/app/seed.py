"""Lệnh seed: tạo trường và admin đầu tiên (không có API tạo trường), kèm các môn Toán, Lý, Hóa.

    uv run python -m app.seed --school-code nd --school-name "THPT Nguyễn Du" \\
        --admin-email admin@nd.vn --admin-name "Quản trị" --admin-password ...

Mỗi tham số có thể lấy từ biến môi trường SEED_SCHOOL_CODE, SEED_SCHOOL_NAME, SEED_ADMIN_EMAIL, SEED_ADMIN_NAME,
SEED_ADMIN_PASSWORD (mật khẩu nên đi qua biến môi trường để không lộ trong `ps`). Cờ --if-missing: nếu trường hoặc
email admin đã có thì thoát 0, không đổi gì (dùng cho deploy tự động, chạy lại an toàn).
"""

import argparse
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import School, Subject, User
from app.models.enums import UserRole

# Tên khớp dòng "Môn:" của ma trận (SUBJECT_CODES).
SUBJECTS = {"toan": "Toán học", "ly": "Vật lí", "hoa": "Hoá học"}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def seed(
    session: Session,
    school_code: str,
    school_name: str,
    admin_email: str,
    admin_password: str,
    admin_name: str,
) -> tuple[School, User]:
    email = normalize_email(admin_email)
    if session.scalar(select(School).where(School.code == school_code)):
        raise ValueError(f"Trường {school_code} đã tồn tại")
    if session.scalar(select(User).where(User.email == email)):
        raise ValueError(f"Email {email} đã được dùng")
    for code, name in SUBJECTS.items():
        if not session.scalar(select(Subject).where(Subject.code == code)):
            session.add(Subject(code=code, name=name))
    school = School(code=school_code, name=school_name)
    session.add(school)
    session.flush()
    admin = User(
        school_id=school.id, email=email, password_hash=hash_password(admin_password),
        full_name=admin_name, role=UserRole.admin,
    )  # fmt: skip
    session.add(admin)
    session.commit()
    return school, admin


def seed_if_missing(
    session: Session,
    school_code: str,
    school_name: str,
    admin_email: str,
    admin_password: str,
    admin_name: str,
) -> tuple[School, User] | None:
    """Như seed(), nhưng trả None (không đổi gì) nếu trường hoặc email admin đã có."""
    email = normalize_email(admin_email)
    if session.scalar(select(School).where(School.code == school_code)) or session.scalar(
        select(User).where(User.email == email)
    ):
        return None
    return seed(session, school_code, school_name, admin_email, admin_password, admin_name)


def main() -> None:
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description="Tạo trường và admin đầu tiên")
    for flag in ("--school-code", "--school-name", "--admin-email", "--admin-name", "--admin-password"):
        env = "SEED_" + flag[2:].upper().replace("-", "_")
        parser.add_argument(flag, default=os.environ.get(env) or None, help=f"hoặc biến môi trường {env}")
    parser.add_argument("--if-missing", action="store_true", help="đã có trường/email thì thoát 0, không đổi gì")
    args = parser.parse_args()
    values = [args.school_code, args.school_name, args.admin_email, args.admin_password, args.admin_name]
    if not all(values):
        parser.error("thiếu tham số (hoặc biến môi trường SEED_*)")
    with SessionLocal() as session:
        result = (seed_if_missing if args.if_missing else seed)(session, *values)
        if result is None:
            print(f"Trường {args.school_code} hoặc admin {args.admin_email} đã có, bỏ qua")
            return
        school, admin = result
        print(f"Đã tạo trường {school.name} ({school.code}) và admin {admin.email}")


if __name__ == "__main__":
    main()
