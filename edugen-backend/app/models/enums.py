"""Các giá trị enum dùng chung.

QuestionType và Level giữ đúng giá trị trong payload ô gửi RAG. Level cũng là chữ trên
tiêu đề cột của ma trận (Biết | Hiểu | Vận dụng) nên parser so khớp thẳng.
"""

import enum


class UserRole(str, enum.Enum):
    teacher = "teacher"
    admin = "admin"


class IngestStatus(str, enum.Enum):
    pending = "pending"  # đã lưu, chưa gửi RAG
    needs_review = "needs_review"  # đề mẫu (T-050): đã có bản nháp, chờ GV duyệt rồi mới gửi RAG
    sent = "sent"  # RAG đã nhận, đang học
    ingested = "ingested"
    failed = "failed"


class MatrixStatus(str, enum.Enum):
    uploaded = "uploaded"  # đã lưu ảnh/PDF, chờ job đọc ma trận
    converting = "converting"  # Gemini đang đọc file
    parsed = "parsed"  # parse được, khớp hàng tổng, chờ GV xác nhận
    invalid = "invalid"  # có lỗi parse hoặc lệch tổng, GV phải sửa ô
    confirmed = "confirmed"  # GV đã xác nhận, được sinh đề
    failed = "failed"  # đọc file lỗi


class QuestionType(str, enum.Enum):
    multiple_choice = "multiple_choice"  # Phần I
    true_false = "true_false"  # Phần II, 4 ý a–d
    short_answer = "short_answer"  # Phần III


class Level(str, enum.Enum):
    biet = "Biết"
    hieu = "Hiểu"
    van_dung = "Vận dụng"


# Thứ tự tăng dần độ khó; dùng để lấy mức cao nhất của 4 ý Đúng–Sai.
LEVEL_ORDER: list[Level] = [Level.biet, Level.hieu, Level.van_dung]


class CellRunStatus(str, enum.Enum):
    complete = "complete"  # đủ câu
    short = "short"  # RAG loại bớt câu không hợp lệ, không tự bù
    error = "error"  # LLMError


class ExamStatus(str, enum.Enum):
    generating = "generating"  # job gọi RAG từng ô đang chạy
    generated = "generated"  # mọi ô đủ câu
    incomplete = "incomplete"  # còn ô thiếu câu hoặc ô lỗi
    failed = "failed"  # không ô nào sinh được
    approved = "approved"  # GV đã duyệt: khoá sửa, được xuất file và nạp ngân hàng


class ExportVariant(str, enum.Enum):
    student = "student"  # chỉ đề
    teacher = "teacher"  # đề + đáp án + lời giải


class ExportFormat(str, enum.Enum):
    docx = "docx"
