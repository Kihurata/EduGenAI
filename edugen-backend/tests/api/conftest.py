"""Client API cho test: DB SQLite, storage thư mục tạm, marker giả, RAG giả lập từ mẫu."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.login_throttle import login_throttle
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.main import app
from app.models import School, User
from app.models.enums import UserRole
from app.seed import seed
from app.services.draft_extractor import get_draft_extractor
from app.services.matrix_converter import get_matrix_converter
from app.services.rag_client import get_rag_client
from app.services.rag_mock import SampleRag
from app.services.storage import LocalStorage, get_storage

FIXTURES = Path(__file__).parents[1] / "fixtures"
MATRIX_MD = FIXTURES / "matrices" / "ktgk_hk1_toan10.md"
MATRIX_PNG = FIXTURES / "matrices" / "ktgk_hk1_toan10.png"
SAMPLES = FIXTURES / "rag" / "ket_qua_mau.json"
PASSWORD = "matkhau-123"


class FakeConverter:
    def __init__(self) -> None:
        self.markdown = MATRIX_MD.read_text(encoding="utf-8")

    def convert(self, source: Path) -> str:
        assert source.exists()
        return self.markdown


class FakeIngestRag(SampleRag):
    """RAG giả lập có thêm endpoint học đề mẫu."""

    def __init__(self, samples) -> None:
        super().__init__(samples)
        self.ingested: list[dict] = []
        self.ingest_error: Exception | None = None
        self.job_status = "done"

    def ingest(self, data: bytes, filename: str, meta: dict) -> str:
        if self.ingest_error:
            raise self.ingest_error
        self.ingested.append({"data": data, "filename": filename, "meta": meta})
        return f"job-{len(self.ingested)}"

    def ingest_status(self, job_id: str) -> tuple[str, str | None]:
        return self.job_status, None


LY_DRAFT = {
    "exam": "Đề thi thử Vật lí 2026", "ma_de": "101", "subject": "toan", "grade": 12, "official": True,
    "questions": [
        {"part": "I", "cau": 1, "topic": "ly/vat_li_nhiet", "stem": "Nhiệt độ sôi của nước ở 1 atm là",
         "options": {"A": "0 °C", "B": "100 °C", "C": "273 K", "D": "50 °C"}, "answer": "B"},
        {"part": "III", "cau": 1, "topic": "", "stem": "Đổi 27 °C sang K.", "answer": "300"},
    ],
}  # fmt: skip  — LLM output: wrong subject/official on purpose, second question has no topic yet


class FakeDraftExtractor:
    """LLM giả đọc đề: trả bản nháp cố định (hoặc lỗi) và ghi lại các lần gọi."""

    def __init__(self) -> None:
        import copy

        self.draft = copy.deepcopy(LY_DRAFT)
        self.error: Exception | None = None
        self.calls: list[dict] = []

    def extract(self, data: bytes, filename: str, subject: str, grade: int) -> dict:
        self.calls.append({"data": data, "filename": filename, "subject": subject, "grade": grade})
        if self.error:
            raise self.error
        return self.draft


@pytest.fixture
def extractor() -> FakeDraftExtractor:
    return FakeDraftExtractor()


@pytest.fixture(autouse=True)
def fast_password_hash(monkeypatch):
    monkeypatch.setattr(settings, "password_hash_iterations", 1000)


@pytest.fixture(autouse=True)
def fresh_login_throttle():
    login_throttle.reset()
    yield
    login_throttle.reset()


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def converter() -> FakeConverter:
    return FakeConverter()


@pytest.fixture
def rag() -> FakeIngestRag:
    import json

    return FakeIngestRag(json.loads(SAMPLES.read_text(encoding="utf-8")))


@pytest.fixture
def client(session_factory, storage, converter, rag, extractor):
    app.dependency_overrides.update({
        get_session_factory: lambda: session_factory,
        get_storage: lambda: storage,
        get_matrix_converter: lambda: converter,
        get_rag_client: lambda: rag,
        get_draft_extractor: lambda: extractor,
    })  # fmt: skip
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def school(db) -> School:
    school, _ = seed(db, "nd", "THPT Nguyễn Du", "admin@nd.vn", PASSWORD, "Quản trị ND")
    return school


def add_user(db, school: School, email: str, role=UserRole.teacher, active=True) -> User:
    user = User(
        school_id=school.id, email=email, password_hash=hash_password(PASSWORD),
        full_name=email.split("@")[0], role=role, is_active=active,
    )  # fmt: skip
    db.add(user)
    db.commit()
    return user


def login(client, email: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def teacher(db, school) -> User:
    return add_user(db, school, "gv1@nd.vn")


@pytest.fixture
def admin_headers(client, school):
    return login(client, "admin@nd.vn")


@pytest.fixture
def teacher_headers(client, teacher):
    return login(client, "gv1@nd.vn")


@pytest.fixture
def colleague_headers(client, db, school):
    add_user(db, school, "gv2@nd.vn")
    return login(client, "gv2@nd.vn")


@pytest.fixture
def outsider_headers(client, db, school):
    """GV của trường khác."""
    other, _ = seed(db, "lqd", "THPT Lê Quý Đôn", "admin@lqd.vn", PASSWORD, "Quản trị LQĐ")
    add_user(db, other, "gv@lqd.vn")
    return login(client, "gv@lqd.vn")


@pytest.fixture
def outsider_admin_headers(client, db, school):
    """Admin của trường khác."""
    seed(db, "lqd", "THPT Lê Quý Đôn", "admin@lqd.vn", PASSWORD, "Quản trị LQĐ")
    return login(client, "admin@lqd.vn")
