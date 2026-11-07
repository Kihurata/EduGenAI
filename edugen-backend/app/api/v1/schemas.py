"""Schema request/response của API v1."""

import uuid
from typing import Annotated

from pydantic import BaseModel, Field

from app.models import User
from app.models.enums import UserRole

# Mật khẩu mới: tối thiểu 8 ký tự; chặn trên để tránh payload khổng lồ.
NewPassword = Annotated[str, Field(min_length=8, max_length=256)]


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: NewPassword


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SchoolOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    school: SchoolOut

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        s = user.school
        return cls(
            id=user.id, email=user.email, full_name=user.full_name, role=user.role,
            is_active=user.is_active, school=SchoolOut(id=s.id, code=s.code, name=s.name),
        )  # fmt: skip


class TeacherIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    password: NewPassword


class TeacherPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    password: NewPassword | None = None
    is_active: bool | None = None


class IssueOut(BaseModel):
    message: str
    location: str | None = None


class Accepted(BaseModel):
    id: uuid.UUID
    status: str


