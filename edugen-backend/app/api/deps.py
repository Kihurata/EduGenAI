"""Dependency dùng chung của API: user hiện tại, phân quyền theo trường và role."""

import hmac
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_claims, password_fingerprint
from app.db.session import get_db
from app.models import User
from app.models.enums import UserRole

DB = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


def ensure_active(user: User) -> None:
    if not user.is_active or not user.school.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tài khoản đã bị khóa")


def current_user(
    db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    claims = decode_access_claims(credentials.credentials) if credentials else None
    try:
        user = db.get(User, uuid.UUID(claims["sub"])) if claims else None
    except (ValueError, TypeError):
        user = None
    # Token cấp trước lần đổi mật khẩu gần nhất (hoặc không có dấu vân tay) bị từ chối.
    if user is not None and not hmac.compare_digest(
        str(claims.get("pwv", "")), password_fingerprint(user.password_hash)
    ):
        user = None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Chưa đăng nhập hoặc phiên đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )  # fmt: skip
    ensure_active(user)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin được dùng chức năng này")
    return user


Admin = Annotated[User, Depends(require_admin)]


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Không tìm thấy {what}")


def get_in_school(db: Session, model, id_: uuid.UUID, user: User, what: str):
    """Lấy bản ghi theo id trong trường của user; trường khác coi như không tồn tại."""
    obj = db.get(model, id_)
    if obj is None or obj.school_id != user.school_id:
        raise not_found(what)
    return obj


def can_manage(user: User, owner_id: uuid.UUID) -> bool:
    """Người tạo hoặc admin của trường (đã kiểm cùng trường trước đó)."""
    return user.id == owner_id or user.role is UserRole.admin


async def read_upload(file: UploadFile) -> bytes:
    """Đọc file tải lên, từ chối file rỗng hoặc vượt MAX_UPLOAD_MB."""
    limit = settings.max_upload_mb * 1024 * 1024
    too_large = HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE, f"File vượt quá {settings.max_upload_mb} MB"
    )
    if file.size is not None and file.size > limit:
        raise too_large
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise too_large
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File rỗng")
    return data
