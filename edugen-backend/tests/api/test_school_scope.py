"""Phạm vi trường (T-045): Backend lấy trường từ token đã ký (sub → user → school_id trong DB), không bao giờ từ request.

Đầu ra mong muốn:
- Gửi school_id của trường khác qua form, query hay claim thêm trong token đều bị bỏ qua: dữ liệu vẫn thuộc trường của user.
- Token ký bằng khoá khác (giả mạo) → 401, kể cả khi sub là user thật.
- Admin trường khác không liệt kê, đọc, sửa, xác nhận được đề mẫu (404): test_sample_exams.test_other_school_cannot_see.
- Sinh đề: mọi ô gửi RAG mang school_id của trường người gọi, nên truy xuất chỉ thấy đề mẫu trường đó
  (bộ lọc Qdrant theo school_id có test riêng ở tests/rag/unit/storage/test_retrieve_school_isolation.py).
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.security import ALGORITHM, password_fingerprint
from app.models import SampleExam, User
from tests.api.test_exams import confirmed_matrix, create_exam
from tests.api.test_sample_exams import BASE, upload


def user_by_email(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def token(user: User, secret: str | None = None, **extra) -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=5),
              "pwv": password_fingerprint(user.password_hash), **extra}  # fmt: skip
    return {"Authorization": f"Bearer {jwt.encode(claims, secret or settings.jwt_secret, algorithm=ALGORITHM)}"}


def test_school_id_sent_in_the_request_is_ignored(client, db, school, admin_headers, outsider_admin_headers):
    other_school_id = str(user_by_email(db, "admin@lqd.vn").school_id)
    resp = client.post(
        BASE, params={"school_id": other_school_id},
        files={"file": ("de.pdf", b"%PDF-1.7 de", "application/pdf")},
        data={"grade": "12", "title": "Đề", "subject": "ly", "school_id": other_school_id}, headers=admin_headers,
    )  # fmt: skip
    assert resp.status_code == 201, resp.text
    db.expire_all()
    assert str(db.get(SampleExam, uuid.UUID(resp.json()["id"])).school_id) == str(school.id)
    assert client.get(BASE, params={"school_id": other_school_id}, headers=outsider_admin_headers).json() == []
    assert [s["id"] for s in client.get(BASE, headers=admin_headers).json()] == [resp.json()["id"]]


def test_a_school_claim_inside_a_valid_token_is_ignored(client, db, school, outsider_admin_headers):
    theirs = upload(client, outsider_admin_headers).json()["id"]
    other_school_id = str(user_by_email(db, "admin@lqd.vn").school_id)
    headers = token(user_by_email(db, "admin@nd.vn"), school_id=other_school_id)  # correctly signed, but school_id is not a claim we read
    assert client.get(BASE, headers=headers).json() == []
    assert client.get(f"{BASE}/{theirs}", headers=headers).status_code == 404


def test_a_token_signed_with_another_key_is_rejected(client, db, school, outsider_admin_headers):
    theirs = upload(client, outsider_admin_headers).json()["id"]
    forged = token(user_by_email(db, "admin@nd.vn"), secret="not-the-server-secret-" + "x" * 32)
    assert client.get(BASE, headers=forged).status_code == 401
    assert client.get(f"{BASE}/{theirs}", headers=forged).status_code == 401


def test_generation_asks_rag_only_for_the_callers_school(client, school, teacher_headers, outsider_headers, rag,
                                                         monkeypatch):  # fmt: skip
    seen = []
    generate = rag.generate

    def recording(cell):
        seen.append(cell.school_id)
        return generate(cell)

    monkeypatch.setattr(rag, "generate", recording)
    matrix = confirmed_matrix(client, teacher_headers)
    assert create_exam(client, outsider_headers, matrix["id"]).status_code == 404  # cannot borrow another school's matrix
    assert seen == []
    assert create_exam(client, teacher_headers, matrix["id"]).status_code == 202
    assert seen and set(seen) == {str(school.id)}
