import logging
import uuid
from datetime import UTC, datetime
from typing import NoReturn

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.deps import DB, CurrentUser, ensure_active
from app.api.v1.schemas import ChangePasswordIn, LoginIn, RefreshIn, TokenPair, UserOut
from app.core.login_throttle import login_throttle
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models import RefreshToken, User
from app.seed import normalize_email

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("edugen.auth")

INVALID_REFRESH = HTTPException(status.HTTP_401_UNAUTHORIZED, "Phiên đăng nhập không hợp lệ")


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    """Thu hồi mọi refresh token còn sống của user (chưa commit)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def _issue(db: DB, user: User) -> TokenPair:
    # Dọn refresh token đã hết hạn của user để bảng không phình mãi.
    db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.expires_at < datetime.now(UTC)),
        execution_options={"synchronize_session": "fetch"},
    )
    token, token_hash, expires_at = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()
    access = create_access_token(str(user.id), user.password_hash)
    return TokenPair(access_token=access, refresh_token=token)


def _find_refresh(db: DB, token: str) -> RefreshToken | None:
    return db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))


def _is_live(row: RefreshToken) -> bool:
    if row.revoked_at is not None:
        return False
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    return expires_at > datetime.now(UTC)


def _check_throttle(key: str) -> None:
    wait = login_throttle.retry_after(key)
    if wait:
        log.warning("auth throttled key=%s retry_after=%s", key, wait)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Nhập sai mật khẩu quá nhiều lần, vui lòng thử lại sau",
            headers={"Retry-After": str(wait)},
        )  # fmt: skip


@router.post("/login")
def login(body: LoginIn, request: Request, db: DB) -> TokenPair:
    email = normalize_email(body.email)
    key = f"{request.client.host if request.client else '-'}|{email}"
    _check_throttle(key)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        hash_password(body.password)  # tốn thời gian như khi có user, tránh dò email qua độ trễ
    if user is None or not verify_password(body.password, user.password_hash):
        login_throttle.record_failure(key)
        log.info("login failed key=%s", key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")
    login_throttle.reset(key)
    ensure_active(user)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    return _issue(db, user)


def _reject_reuse(db: Session, user_id: uuid.UUID) -> NoReturn:
    log.warning("refresh token reuse detected user_id=%s; revoking all sessions", user_id)
    revoke_all_sessions(db, user_id)
    db.commit()
    raise INVALID_REFRESH


@router.post("/refresh")
def refresh(body: RefreshIn, db: DB) -> TokenPair:
    row = _find_refresh(db, body.refresh_token)
    if row is None:
        raise INVALID_REFRESH
    if row.revoked_at is not None:
        # Token đã dùng/thu hồi bị gửi lại: có thể đã lộ → đăng xuất mọi phiên của user.
        _reject_reuse(db, row.user_id)
    if not _is_live(row):
        raise INVALID_REFRESH
    ensure_active(row.user)
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC)),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        # Request khác đã dùng token sau lúc đọc: xử lý như token bị tái sử dụng.
        _reject_reuse(db, row.user_id)
    return _issue(db, row.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: DB) -> Response:
    row = _find_refresh(db, body.refresh_token)
    if row is not None and _is_live(row):
        row.revoked_at = datetime.now(UTC)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: CurrentUser, db: DB) -> Response:
    """Thu hồi refresh token ở mọi thiết bị; access token còn lại tự hết hạn sau tối đa vài chục phút."""
    revoke_all_sessions(db, user.id)
    db.commit()
    log.info("logout-all user_id=%s", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: CurrentUser, db: DB) -> TokenPair:
    """Đổi mật khẩu của chính mình: mọi phiên khác bị đăng xuất, trả cặp token mới cho phiên hiện tại."""
    key = f"pw|{user.id}"
    _check_throttle(key)
    if not verify_password(body.current_password, user.password_hash):
        login_throttle.record_failure(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu hiện tại không đúng")
    login_throttle.reset(key)
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu mới phải khác mật khẩu hiện tại")
    user.password_hash = hash_password(body.new_password)
    revoke_all_sessions(db, user.id)
    log.info("password changed user_id=%s", user.id)
    return _issue(db, user)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_user(user)
