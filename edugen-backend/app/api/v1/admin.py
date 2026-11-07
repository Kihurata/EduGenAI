"""Admin: tạo/khóa tài khoản giáo viên trong trường của mình."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, Admin, get_in_school
from app.api.v1.auth import revoke_all_sessions
from app.api.v1.schemas import TeacherIn, TeacherPatch, UserOut
from app.core.security import hash_password
from app.models import User
from app.models.enums import UserRole
from app.seed import normalize_email

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/teachers", status_code=status.HTTP_201_CREATED)
def create_teacher(body: TeacherIn, db: DB, admin: Admin) -> UserOut:
    email = normalize_email(body.email)
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được dùng")
    teacher = User(
        school_id=admin.school_id, email=email, password_hash=hash_password(body.password),
        full_name=body.full_name, role=UserRole.teacher,
    )  # fmt: skip
    db.add(teacher)
    db.commit()
    return UserOut.from_user(teacher)


@router.get("/teachers")
def list_teachers(db: DB, admin: Admin) -> list[UserOut]:
    teachers = db.scalars(
        select(User)
        .where(User.school_id == admin.school_id, User.role == UserRole.teacher)
        .order_by(User.email)
    )
    return [UserOut.from_user(t) for t in teachers]


@router.patch("/teachers/{teacher_id}")
def update_teacher(teacher_id: uuid.UUID, body: TeacherPatch, db: DB, admin: Admin) -> UserOut:
    teacher = get_in_school(db, User, teacher_id, admin, "giáo viên")
    if teacher.role is not UserRole.teacher:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy giáo viên")
    if body.full_name is not None:
        teacher.full_name = body.full_name
    if body.password is not None:
        teacher.password_hash = hash_password(body.password)
    if body.is_active is not None:
        teacher.is_active = body.is_active
    if body.is_active is False or body.password is not None:
        # Khóa hoặc đổi mật khẩu thì đăng xuất mọi phiên đang mở.
        revoke_all_sessions(db, teacher.id)
    db.commit()
    return UserOut.from_user(teacher)
