"""Ma trận demo Toán 12 (data/demo/matrix_toan12_demo.json) và script tạo nhanh.

Đầu ra mong muốn:
- Fixture đúng cấu trúc 12 TN / 4 Đ-S / 6 TLN, đủ 10 điểm, mọi chủ đề có trong danh sách lớp 12.
- Script tạo ma trận confirmed; GV thấy qua API và sinh đề từ nó được.
"""

import importlib.util
import json
from collections import Counter
from pathlib import Path

from app.domain.topics import find_topic
from app.models.enums import QuestionType
from tests.api.test_exams import BASE as EXAMS

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("create_demo_matrix", ROOT / "scripts" / "create_demo_matrix.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)
FIXTURE = ROOT / "data" / "demo" / "matrix_toan12_demo.json"


def test_fixture_is_a_valid_toan12_matrix():
    parsed = script.load_fixture(FIXTURE)
    assert parsed.issues == []  # gồm tổng điểm = 10
    counts = Counter()
    for cell in parsed.cells:
        counts[cell.type] += cell.count
        assert find_topic(cell.topic, 12, "toan") is not None, cell.topic
    assert counts == {QuestionType.multiple_choice: 12, QuestionType.true_false: 4, QuestionType.short_answer: 6}
    assert json.loads(FIXTURE.read_text(encoding="utf-8"))["duration_minutes"] == 90


def test_script_creates_confirmed_matrix_usable_for_exam(client, db, teacher, teacher_headers):
    matrix = script.create_matrix(db, teacher, script.load_fixture(FIXTURE))
    got = client.get(f"/api/v1/matrices/{matrix.id}", headers=teacher_headers).json()
    assert (got["status"], got["grade"], got["subject"], len(got["cells"])) == ("confirmed", 12, "toan", 12)
    resp = client.post(EXAMS, json={"matrix_id": str(matrix.id), "duration_minutes": 90}, headers=teacher_headers)
    assert resp.status_code == 202, resp.text


def test_script_is_idempotent_by_name(db, teacher):
    parsed = script.load_fixture(FIXTURE)
    assert script.find_existing(db, teacher, parsed.name) is None
    matrix = script.create_matrix(db, teacher, parsed)
    assert script.find_existing(db, teacher, parsed.name).id == matrix.id
