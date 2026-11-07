import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPkMixin
from app.models.catalog import School
from app.models.enums import UserRole
from app.models.types import pg_enum


class User(UUIDPkMixin, TimestampMixin, Base):
    """Giáo viên hoặc admin của đúng một trường."""

    __tablename__ = "users"

    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    # Email lưu dạng chữ thường (service chịu trách nhiệm normalize trước khi ghi).
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), default=UserRole.teacher
    )
    is_active: Mapped[bool] = mapped_column(default=True)  # admin khóa tài khoản GV

    school: Mapped[School] = relationship()
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class RefreshToken(UUIDPkMixin, CreatedAtMixin, Base):
    """Refresh token cho JWT. Chỉ lưu hash; logout = đặt revoked_at."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
