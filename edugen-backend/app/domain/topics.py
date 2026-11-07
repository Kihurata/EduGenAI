"""Mã chủ đề dùng chung với RAG: Toán (rag.vocab.TOPICS, D-008 §3), Lý và Hóa (D-013).

Chép từ vault 06-testing/fixtures/toan-matrix/Toán topic list.md: mỗi mã là một chương SGK
Kết nối tri thức, thuộc một mạch. Đổi danh sách bên đó thì đổi ở đây.
Lý và Hóa chép từ vault 06-testing/fixtures/ly-hoa/Lý và Hóa topic list.md: phần mạch là mã môn,
nên mã RAG là "ly/<mã>" hoặc "hoa/<mã>".
"""

import re
import unicodedata
from dataclasses import dataclass

DS, HH, TK = "dai_so_giai_tich", "hinh_hoc_do_luong", "thong_ke_xac_suat"


@dataclass(frozen=True)
class Topic:
    code: str
    strand: str
    name: str  # tên chương tiếng Việt như trong SGK
    subject: str = "toan"


TOPICS: dict[str, Topic] = {
    t.code: t
    for t in (
        Topic("ung_dung_dao_ham", DS, "Ứng dụng đạo hàm để khảo sát và vẽ đồ thị hàm số"),
        Topic("vecto_khong_gian", HH, "Vectơ và hệ trục tọa độ trong không gian"),
        Topic("thong_ke_phan_tan", TK, "Các số đặc trưng đo mức độ phân tán của mẫu số liệu ghép nhóm"),
        Topic("nguyen_ham_tich_phan", DS, "Nguyên hàm và tích phân"),
        Topic("toa_do_khong_gian", HH, "Phương pháp tọa độ trong không gian"),
        Topic("xac_suat_co_dieu_kien", TK, "Xác suất có điều kiện"),
        Topic("luong_giac", DS, "Hàm số lượng giác và phương trình lượng giác"),
        Topic("day_so_cap_so", DS, "Dãy số. Cấp số cộng và cấp số nhân"),
        Topic("thong_ke_trung_tam", TK, "Các số đặc trưng đo xu thế trung tâm của mẫu số liệu ghép nhóm"),
        Topic("quan_he_song_song", HH, "Quan hệ song song trong không gian"),
        Topic("mu_logarit", DS, "Hàm số mũ và hàm số lôgarit"),
        Topic("quan_he_vuong_goc", HH, "Quan hệ vuông góc trong không gian"),
        Topic("xac_suat_quy_tac", TK, "Các quy tắc tính xác suất"),
        Topic("dao_ham", DS, "Đạo hàm"),
        Topic("he_bat_phuong_trinh_bac_nhat_hai_an", DS, "Bất phương trình và hệ bất phương trình bậc nhất hai ẩn"),
        Topic("ham_so_bac_hai", DS, "Hàm số, đồ thị và ứng dụng"),
        Topic("to_hop", DS, "Đại số tổ hợp"),
        Topic("xac_suat_co_dien", TK, "Tính xác suất theo định nghĩa cổ điển"),
        Topic("he_phuong_trinh_bac_nhat_ba_an", DS, "Hệ phương trình bậc nhất ba ẩn"),
    )
}  # fmt: skip

# (mã, tên chương KNTT, lớp) — D-013.
_LY = (
    ("mo_dau", "Mở đầu", 10),
    ("dong_hoc", "Động học", 10),
    ("dong_luc_hoc", "Động lực học", 10),
    ("nang_luong_cong_cong_suat", "Năng lượng, công, công suất", 10),
    ("dong_luong", "Động lượng", 10),
    ("chuyen_dong_tron", "Chuyển động tròn", 10),
    ("bien_dang_vat_ran", "Biến dạng của vật rắn", 10),
    ("dao_dong", "Dao động", 11),
    ("song", "Sóng", 11),
    ("dien_truong", "Điện trường", 11),
    ("dong_dien_mach_dien", "Dòng điện, mạch điện", 11),
    ("vat_li_nhiet", "Vật lí nhiệt", 12),
    ("khi_li_tuong", "Khí lí tưởng", 12),
    ("tu_truong", "Từ trường", 12),
    ("vat_li_hat_nhan", "Vật lí hạt nhân và phóng xạ", 12),
)
_HOA = (
    ("cau_tao_nguyen_tu", "Cấu tạo nguyên tử", 10),
    ("bang_tuan_hoan", "Bảng tuần hoàn các nguyên tố hóa học và định luật tuần hoàn", 10),
    ("lien_ket_hoa_hoc", "Liên kết hóa học", 10),
    ("phan_ung_oxi_hoa_khu", "Phản ứng oxi hóa – khử", 10),
    ("nang_luong_hoa_hoc", "Năng lượng hóa học", 10),
    ("toc_do_phan_ung", "Tốc độ phản ứng", 10),
    ("halogen", "Nguyên tố nhóm VIIA (halogen)", 10),
    ("phong_chong_chay_no", "Hóa học về phòng chống cháy nổ", 10),
    ("can_bang_hoa_hoc", "Cân bằng hóa học", 11),
    ("nitrogen_sulfur", "Nitrogen và sulfur", 11),
    ("dai_cuong_huu_co", "Đại cương về hóa học hữu cơ", 11),
    ("hydrocarbon", "Hydrocarbon", 11),
    ("dan_xuat_halogen_alcohol_phenol", "Dẫn xuất halogen – alcohol – phenol", 11),
    ("carbonyl_carboxylic_acid", "Hợp chất carbonyl – carboxylic acid", 11),
    ("phan_bon", "Phân bón", 11),
    ("ester_lipid", "Ester – Lipid", 12),
    ("carbohydrate", "Carbohydrate", 12),
    ("hop_chat_nitrogen", "Hợp chất chứa nitrogen", 12),
    ("polymer", "Polymer", 12),
    ("pin_dien_dien_phan", "Pin điện và điện phân", 12),
    ("dai_cuong_kim_loai", "Đại cương về kim loại", 12),
    ("nhom_ia_iia", "Nguyên tố nhóm IA và nhóm IIA", 12),
    ("kim_loai_chuyen_tiep", "Sơ lược về dãy kim loại chuyển tiếp thứ nhất và phức chất", 12),
)
_SCIENCE_GRADES = {code: grade for _, rows in (("ly", _LY), ("hoa", _HOA)) for code, _, grade in rows}
TOPICS |= {code: Topic(code, subject, name, subject) for subject, rows in (("ly", _LY), ("hoa", _HOA))
           for code, name, _ in rows}


def topic_list_name(subject: str) -> str:
    """Tên ghi chú danh sách chủ đề trong vault, dùng trong thông báo lỗi."""
    return "Toán topic list" if subject == "toan" else "Lý và Hóa topic list"


def topics_for(subject: str) -> list[Topic]:
    """Chủ đề của một môn, theo thứ tự trong danh sách (lớp 10 → 12 với Lý/Hóa)."""
    return [t for t in TOPICS.values() if t.subject == subject]


def _key(text: str) -> str:
    """So khớp không phân biệt hoa thường, dấu câu, khoảng trắng; NFC vì marker có thể trả NFD."""
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


_BY_NAME: dict[str, list[Topic]] = {}
for _t in TOPICS.values():
    _BY_NAME.setdefault(_key(_t.name), []).append(_t)

# The matrix writer often shortens a chapter title to one of these labels.  Keep
# these aliases here (rather than in the RAG vocabulary): they are input labels,
# not additional index topics.
_TOPIC_GRADES = {
    # Toán 10
    "he_bat_phuong_trinh_bac_nhat_hai_an": 10,
    "ham_so_bac_hai": 10,
    "to_hop": 10,
    "xac_suat_co_dien": 10,
    "he_phuong_trinh_bac_nhat_ba_an": 10,
    # Toán 11
    "luong_giac": 11,
    "day_so_cap_so": 11,
    "thong_ke_trung_tam": 11,
    "quan_he_song_song": 11,
    "mu_logarit": 11,
    "quan_he_vuong_goc": 11,
    "xac_suat_quy_tac": 11,
    "dao_ham": 11,
    # Toán 12
    "ung_dung_dao_ham": 12,
    "vecto_khong_gian": 12,
    "thong_ke_phan_tan": 12,
    "nguyen_ham_tich_phan": 12,
    "toa_do_khong_gian": 12,
    "xac_suat_co_dieu_kien": 12,
} | _SCIENCE_GRADES

_ALIASES = {
    _key("Hàm số"): [("ham_so_bac_hai", 10)],
    _key("Hàm số và đồ thị"): [("ham_so_bac_hai", 10)],
    _key("Thống kê"): [("thong_ke_trung_tam", 11), ("thong_ke_phan_tan", 12)],
    _key("Xác suất"): [("xac_suat_co_dien", 10)],
}


def _without_chapter_prefix(key: str) -> str:
    """Remove the optional school/book/chapter decoration from a label."""
    return re.sub(
        r"^(?:(?:toán|toan|lớp|lop) (?:10|11|12) )?(?:chương|chuong) (?:[ivx]+|\d+)\s+",
        "",
        key,
    )


def topic_grade(topic: Topic, default: int) -> int:
    """Lớp của chương (SGK KNTT); mã chưa xếp lớp thì lấy lớp của ma trận."""
    return _TOPIC_GRADES.get(topic.code, default)


def find_topic(text: str, grade: int | None = None, subject: str | None = None) -> Topic | None:
    """Map a teacher's chapter label to a RAG topic.

    ``grade`` is optional for backwards compatibility.  It is required for
    ambiguous short labels such as ``Thống kê`` and disambiguates labels such
    as ``Hàm số`` when a matrix carries its grade separately.  A full chapter
    name resolves for its own grade and every higher one: a grade-12 (TN THPT)
    matrix also covers grade 10-11 chapters (D-009), a grade-10 one never
    covers grade-12 chapters.  ``subject`` limits the match to that subject's
    topics (None: any subject, for older callers that only knew Toán).
    """
    key = _key(text)
    candidates = [key, _without_chapter_prefix(key)]
    for candidate in candidates:
        if candidate in _ALIASES and subject in (None, "toan"):  # aliases are Toán labels
            for code, alias_grade in _ALIASES[candidate]:
                if grade is None:
                    # Ambiguous shorthand must not silently select a grade.
                    continue
                if grade == alias_grade:
                    return TOPICS[code]
            continue
        for topic in _BY_NAME.get(candidate, ()):
            if subject not in (None, topic.subject):
                continue
            if grade is None or _TOPIC_GRADES.get(topic.code, grade) <= grade:
                return topic
    return None
