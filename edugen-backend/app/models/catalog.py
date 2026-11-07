"""Trường (tenant) và danh mục môn học dùng chung mọi trường."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPkMixin


class School(UUIDPkMixin, CreatedAtMixin, Base):
    """Một trường dùng hệ thống. Tạo bằng lệnh seed, không có API tạo trường."""

    __tablename__ = "schools"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))  # in lên đầu đề
    is_active: Mapped[bool] = mapped_column(default=True)


class Subject(UUIDPkMixin, Base):
    __tablename__ = "subjects"

    code: Mapped[str] = mapped_column(String(32), unique=True)  # toan
    name: Mapped[str] = mapped_column(String(100))  # "Toán học", khớp dòng "Môn:" của ma trận
