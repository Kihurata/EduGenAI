"""Ma trận: tải ảnh/PDF → job marker nền → GV xem, sửa ô → bắt buộc xác nhận.

Đầu ra mong muốn:
- Tải lên trả matrix_id ngay (202); job nền chạy xong thì GET thấy parsed và 18 ô.
- Chỉ nhận PNG/JPG/PDF. Chỉ người tạo hoặc admin cùng trường xem/sửa; trường khác → 404.
- Sửa ô thì đối chiếu lại hàng tổng của ma trận gốc: lệch → invalid, khớp → parsed.
- Chỉ xác nhận được ma trận parsed; đã xác nhận thì không sửa được nữa.
"""

from app.services.matrix_converter import ConversionError
from tests.api.conftest import MATRIX_PNG

BASE = "/api/v1/matrices"


def upload(client, headers, name="mt.png", data=None, mime="image/png"):
    data = MATRIX_PNG.read_bytes() if data is None else data
    return client.post(BASE, files={"file": (name, data, mime)}, headers=headers)


def uploaded(client, headers) -> dict:
    resp = upload(client, headers)
    assert resp.status_code == 202, resp.text
    return client.get(f"{BASE}/{resp.json()['id']}", headers=headers).json()


def editable(cells: list[dict]) -> list[dict]:
    keys = ("topic", "content_unit", "type", "level", "count", "statement_levels", "competency_codes")
    return [{k: c[k] for k in keys} for c in cells]


def test_upload_returns_id_then_background_job_parses(client, teacher_headers, storage):
    resp = upload(client, teacher_headers)
    assert resp.status_code == 202
    assert resp.json()["status"] == "uploaded"
    m = client.get(f"{BASE}/{resp.json()['id']}", headers=teacher_headers).json()
    assert m["status"] == "parsed"
    assert (m["subject"], m["grade"], m["name"]) == ("toan", 10, "KTGK - HK1 - 10")
    assert m["source_filename"] == "mt.png"
    assert m["issues"] == []
    assert len(m["cells"]) == 18
    assert m["cells"][10]["statement_levels"] == ["Biết", "Biết", "Hiểu", "Hiểu"]
    assert m["cells"][10]["content_unit"] is None
    assert storage.path(f"matrices/{m['id']}/source.png").read_bytes() == MATRIX_PNG.read_bytes()


def test_only_images_and_pdf_are_accepted(client, teacher_headers):
    resp = upload(client, teacher_headers, "mt.txt", b"abc", "text/plain")
    assert resp.status_code == 415
    assert resp.json()["detail"] == "Chỉ nhận ảnh PNG/JPG hoặc file PDF"
    assert upload(client, teacher_headers, "mt.pdf", b"", "application/pdf").status_code == 400


def test_marker_failure_is_visible(client, teacher_headers, converter, monkeypatch):
    def broken(source):
        raise ConversionError("Marker lỗi: hết bộ nhớ")

    monkeypatch.setattr(converter, "convert", broken)
    m = uploaded(client, teacher_headers)
    assert m["status"] == "failed"
    assert "hết bộ nhớ" in m["error_message"]


def test_unexpected_matrix_error_hides_raw_message(client, teacher_headers, converter, monkeypatch):
    def broken(source):
        raise RuntimeError("segfault 0xdead")

    monkeypatch.setattr(converter, "convert", broken)
    m = uploaded(client, teacher_headers)
    assert m["status"] == "failed"
    assert "0xdead" not in m["error_message"]
    assert m["error_message"].startswith("Lỗi hệ thống")


def test_list_shows_own_matrices(client, teacher_headers, colleague_headers):
    mine = uploaded(client, teacher_headers)
    uploaded(client, colleague_headers)
    listed = client.get(BASE, headers=teacher_headers).json()
    assert [m["id"] for m in listed] == [mine["id"]]
    assert listed[0]["name"] == "KTGK - HK1 - 10"


def test_access_is_owner_or_admin_of_same_school(client, teacher_headers, colleague_headers, admin_headers, outsider_headers):
    m = uploaded(client, teacher_headers)
    assert client.get(f"{BASE}/{m['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{BASE}/{m['id']}", headers=colleague_headers).status_code == 404
    assert client.get(f"{BASE}/{m['id']}", headers=outsider_headers).status_code == 404


def test_editing_cells_rechecks_declared_totals(client, teacher_headers):
    m = uploaded(client, teacher_headers)
    cells = editable(m["cells"])
    cells[0]["count"] = 3
    resp = client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "invalid"
    assert any("Tổng số câu ghi" in i["message"] for i in resp.json()["issues"])

    cells[0]["count"] = 2
    cells[0]["topic"] = "Mệnh đề"
    resp = client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells, "name": "Giữa kì 1"}, headers=teacher_headers)
    body = resp.json()
    assert (body["status"], body["issues"], body["name"]) == ("parsed", [], "Giữa kì 1")
    assert body["cells"][0]["topic"] == "Mệnh đề"


def test_true_false_cell_needs_four_statement_levels_and_level_is_their_max(client, teacher_headers):
    m = uploaded(client, teacher_headers)
    cells = editable(m["cells"])
    cells[10]["statement_levels"] = ["Biết", "Biết", "Hiểu"]
    assert client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers).status_code == 422
    cells[10]["statement_levels"] = ["Biết", "Biết", "Hiểu", "Hiểu"]
    cells[10]["level"] = "Biết"
    body = client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers).json()
    assert body["cells"][10]["level"] == "Hiểu"
    cells[0]["statement_levels"] = ["Biết"] * 4  # câu nhiều lựa chọn không có ý a–d
    assert client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers).status_code == 422


def test_confirm_only_parsed_matrix_and_lock_after(client, teacher_headers):
    m = uploaded(client, teacher_headers)
    cells = editable(m["cells"])
    cells[0]["count"] = 5
    client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers)
    resp = client.post(f"{BASE}/{m['id']}/confirm", headers=teacher_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Ma trận còn lỗi hoặc chưa đọc xong, chưa xác nhận được"

    cells[0]["count"] = 2
    client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells, "grade": 12}, headers=teacher_headers)
    resp = client.post(f"{BASE}/{m['id']}/confirm", headers=teacher_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed" and resp.json()["confirmed_at"]
    resp = client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers)
    assert resp.status_code == 409


def test_cell_with_zero_or_negative_count_is_rejected(client, teacher_headers):
    """T-017: ô ma trận có count 0 hoặc âm bị từ chối (422), ma trận không đổi."""
    m = uploaded(client, teacher_headers)
    for bad in (0, -1):
        cells = editable(m["cells"])
        cells[0]["count"] = bad
        resp = client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers)
        assert resp.status_code == 422, resp.text
    assert client.get(f"{BASE}/{m['id']}", headers=teacher_headers).json()["cells"] == m["cells"]


def test_true_false_statement_units_are_saved_and_checked(client, teacher_headers):
    m = uploaded(client, teacher_headers)
    cells = editable(m["cells"])
    tf = next(i for i, c in enumerate(cells) if c["type"] == "true_false")
    units = ["Mệnh đề", "Tập hợp", None, "Tập hợp"]
    cells[tf]["statement_units"] = units
    body = client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers).json()
    assert body["cells"][tf]["statement_units"] == units
    cells[tf]["statement_units"] = ["Mệnh đề"] * 3  # cần đúng 4 ý
    assert client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers).status_code == 422
    cells[tf]["statement_units"] = units
    cells[0]["statement_units"] = ["Mệnh đề"] * 4  # câu nhiều lựa chọn không có ý a–d
    assert client.put(f"{BASE}/{m['id']}/cells", json={"cells": cells}, headers=teacher_headers).status_code == 422


def test_confirm_rejects_non_grade_12_matrix_without_rewriting_its_grade(client, teacher_headers):
    m = uploaded(client, teacher_headers)  # ma trận mẫu là lớp 10
    resp = client.post(f"{BASE}/{m['id']}/confirm", headers=teacher_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Bản demo hiện chỉ hỗ trợ Toán lớp 12. Ma trận này là lớp 10 nên chưa xác nhận được."
    assert client.get(f"{BASE}/{m['id']}", headers=teacher_headers).json()["grade"] == 10


def test_matrix_with_missing_or_wrong_grade_can_be_set_to_12_then_confirmed(client, db, teacher_headers):
    import uuid

    from app.models import ExamMatrix

    for wrong in (None, 11):
        m = uploaded(client, teacher_headers)
        row = db.get(ExamMatrix, uuid.UUID(m["id"]))
        row.grade = wrong
        db.commit()
        assert client.post(f"{BASE}/{m['id']}/confirm", headers=teacher_headers).status_code == 409
        resp = client.put(f"{BASE}/{m['id']}/cells", json={"cells": editable(m["cells"]), "grade": 12}, headers=teacher_headers)
        assert resp.status_code == 200 and resp.json()["grade"] == 12 and resp.json()["status"] == "parsed"
        assert client.post(f"{BASE}/{m['id']}/confirm", headers=teacher_headers).status_code == 200
