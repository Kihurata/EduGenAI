"""Tóm tắt: schema JSON và prompt để Gemini trích ma trận đề (D-016, T-054); chỉ là hằng số, logic đọc ở domain/matrix_extract.py."""

from app.domain.topics import TOPICS, topic_grade

_COUNTS = {"type": "OBJECT", "properties": {k: {"type": "INTEGER"} for k in ("biet", "hieu", "van_dung")}}
_ITEM = {
    "type": "OBJECT",
    "properties": {
        "cau": {"type": "STRING", "nullable": True},
        "y": {"type": "STRING", "nullable": True},
        "level": {"type": "STRING", "enum": ["biet", "hieu", "van_dung"]},
    },
}
MATRIX_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "subject": {"type": "STRING"},
        "name": {"type": "STRING", "nullable": True},
        "rows": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "unit_name": {"type": "STRING"},
                    "grade": {"type": "INTEGER", "nullable": True},
                    "topic_code": {"type": "STRING", "nullable": True},
                    "multiple_choice": _COUNTS,
                    "true_false_statements": _COUNTS,
                    "short_answer": _COUNTS,
                    "row_totals": {**_COUNTS, "nullable": True},
                    "true_false_items": {"type": "ARRAY", "items": _ITEM},
                },
            },
        },
    },
}


def _topic_lines() -> str:
    return "\n".join(f"- {t.code} ({t.subject}, lớp {topic_grade(t, 0) or '?'}): {t.name}" for t in TOPICS.values())


PROMPT = f"""Trích ma trận đề kiểm tra trong file thành JSON theo schema, không sửa số, không đoán.
- subject: tên môn như ghi trong file (Toán, Vật lí, Hóa học...). name: tên/tiêu đề ma trận, null nếu không có.
- Mỗi hàng đơn vị kiến thức là một phần tử rows; unit_name chép đúng tên gốc.
- KHÔNG đưa vào rows các hàng tổng/tỉ lệ (Tổng số câu, Tổng số điểm, Tỉ lệ %...) hay hàng chỉ có tên chương mà không có số.
- grade: lớp của hàng (10/11/12), null nếu file không ghi.
- topic_code: chọn trong danh sách mã bên dưới nếu chắc chắn, không chắc hoặc không có thì null.
- multiple_choice (Phần I) và short_answer (Phần III): số CÂU theo mức. Cột không có thì 0.
- true_false_statements (Phần II, đúng-sai): số Ý theo mức (mỗi câu 4 ý), KHÔNG phải số câu.
- Ô ghi mã câu (C1, C2a...) thì đếm số mã.
- Mỗi phần có thể chỉ có vài mức (vd Phần III chỉ có cột Hiểu, VD): xác định mức theo đúng tiêu đề cột phía trên ô, đừng dồn cột.
- row_totals: chép số ở cột "Tổng" bên phải của hàng theo mức Biết/Hiểu/VD (ô trống = 0), null nếu bảng không có cột này. Cột Tổng và Tỉ lệ CHỈ để đối chiếu, KHÔNG cộng vào multiple_choice/true_false_statements/short_answer.
- true_false_items: CHỈ khi file có mã ý (C1a, C1b...), liệt kê từng ý với cau (số câu, ví dụ "C1"), y (chỉ một chữ a-d, ví dụ C1a → cau "C1", y "a") và mức; file không có mã thì để mảng rỗng.
Mã chủ đề:
{_topic_lines()}"""
