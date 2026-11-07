"""Tóm tắt: registry môn học (D-020, T-064): nguồn duy nhất về các môn hệ thống chạy được: mã, tên chính thức, tên ngắn,
các cách ghi tên trên ma trận và tên danh sách chủ đề trong vault. Đọc ma trận, seed, đề mục SGK, prompt sinh câu và API
`/subjects` đều lấy từ đây. Thêm môn = thêm một mục ở đây cùng dữ liệu của môn (cấu trúc đề, chủ đề, cụm truy vấn RAG);
`tests/unit/test_subject_registry.py` chỉ ra còn thiếu gì.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Subject:
    code: str  # mã môn trong DB, ô ma trận và payload Qdrant
    name: str  # tên chính thức, khớp dòng "Môn:" của ma trận và bảng subjects
    label: str  # tên ngắn: đề mục SGK ("Toán 12 > …") và prompt ("môn Vật lí")
    aliases: tuple[str, ...]  # các cách ghi tên môn khác trên ma trận, chữ thường
    topic_list: str  # ghi chú danh sách chủ đề trong vault, dùng trong thông báo lỗi


SUBJECTS: dict[str, Subject] = {
    s.code: s
    for s in (
        Subject("toan", "Toán học", "Toán", ("toán",), "Toán topic list"),
        Subject("ly", "Vật lí", "Vật lí", ("vật lý", "lí", "lý"), "Lý và Hóa topic list"),
        Subject("hoa", "Hoá học", "Hoá học", ("hóa học", "hóa", "hoá"), "Lý và Hóa topic list"),
    )
}

# Tên môn (chữ thường) trên ma trận → mã môn.
SUBJECT_CODES: dict[str, str] = {
    alias: s.code for s in SUBJECTS.values() for alias in (s.name.lower(), s.label.lower(), *s.aliases)
}


def get_subject(code: str) -> Subject:
    try:
        return SUBJECTS[code]
    except KeyError:
        raise ValueError(f"Môn chưa hỗ trợ: {code}") from None
