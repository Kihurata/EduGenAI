"""Tóm tắt: từ vựng chung của hợp đồng RAG với Backend (T-028): loại câu và phần đề, mức độ Biết/Hiểu/Vận dụng, mã chủ đề mới "mạch/chủ đề" (theo "Toán topic list" trong vault) và bảng đổi 31 mã chủ đề cũ mà chỉ mục Qdrant còn lưu; cụm từ tiếng Việt của từng chủ đề (TOPIC_QUERIES, đọc từ storage/topic_queries.json) cho cả truy xuất và prompt sinh câu."""

import json
from pathlib import Path

TYPES = ("multiple_choice", "true_false", "short_answer")
PART_BY_TYPE = {"multiple_choice": "I", "true_false": "II", "short_answer": "III"}
LEVELS = ("Biết", "Hiểu", "Vận dụng")  # ordered low → high
LEVEL_FROM_CODE = {"biet": "Biết", "hieu": "Hiểu", "vandung": "Vận dụng"}  # matrix YAML spelling

TOPICS = {
    "dai_so_giai_tich/ung_dung_dao_ham",
    "hinh_hoc_do_luong/vecto_khong_gian",
    "thong_ke_xac_suat/thong_ke_phan_tan",
    "dai_so_giai_tich/nguyen_ham_tich_phan",
    "hinh_hoc_do_luong/toa_do_khong_gian",
    "thong_ke_xac_suat/xac_suat_co_dieu_kien",
    "dai_so_giai_tich/luong_giac",
    "dai_so_giai_tich/day_so_cap_so",
    "thong_ke_xac_suat/thong_ke_trung_tam",
    "hinh_hoc_do_luong/quan_he_song_song",
    "dai_so_giai_tich/mu_logarit",
    "hinh_hoc_do_luong/quan_he_vuong_goc",
    "thong_ke_xac_suat/xac_suat_quy_tac",
    "dai_so_giai_tich/dao_ham",
    "dai_so_giai_tich/he_bat_phuong_trinh_bac_nhat_hai_an",
    "dai_so_giai_tich/ham_so_bac_hai",
    "dai_so_giai_tich/to_hop",
    "thong_ke_xac_suat/xac_suat_co_dien",
    "dai_so_giai_tich/he_phuong_trinh_bac_nhat_ba_an",
    "dai_so_giai_tich/menh_de_tap_hop",
    "hinh_hoc_do_luong/he_thuc_luong_tam_giac",
    "hinh_hoc_do_luong/vecto_mat_phang",
    "thong_ke_xac_suat/thong_ke_khong_ghep_nhom",
    "hinh_hoc_do_luong/toa_do_mat_phang",
    "dai_so_giai_tich/gioi_han_ham_lien_tuc",
}

_D, _H, _T = "dai_so_giai_tich/", "hinh_hoc_do_luong/", "thong_ke_xac_suat/"

# D-021: payload `chapter` of each Toán topic in the SGK Kết nối tri thức index (exact match); a topic missing here (and every
# non-Toán one) is searched by grade only. Another SGK set needs another table.
CHAPTER_BY_TOPIC = {
    _D + "he_bat_phuong_trinh_bac_nhat_hai_an": "Chương II. Bất phương trình và hệ bất phương trình bậc nhất hai ẩn",
    _D + "ham_so_bac_hai": "Chương VI. Hàm số, đồ thị và ứng dụng",
    _D + "to_hop": "Chương VIII. Đại số tổ hợp",
    _T + "xac_suat_co_dien": "Chương IX. Tính xác suất theo định nghĩa cổ điển",
    _D + "luong_giac": "Chương I. Hàm số lượng giác và phương trình lượng giác",
    _D + "day_so_cap_so": "Chương II. Dãy số. Cấp số cộng và cấp số nhân",
    _T + "thong_ke_trung_tam": "Chương III. Các số đặc trưng đo xu thế trung tâm của mẫu số liệu ghép nhóm",
    _H + "quan_he_song_song": "Chương IV. Quan hệ song song trong không gian",
    _D + "mu_logarit": "Chương VI. Hàm số mũ và hàm số lôgarit",
    _H + "quan_he_vuong_goc": "Chương VII. Quan hệ vuông góc trong không gian",
    _T + "xac_suat_quy_tac": "Chương VIII. Các quy tắc tính xác suất",
    _D + "dao_ham": "Chương IX. Đạo hàm",
    _D + "menh_de_tap_hop": "Chương I. Mệnh đề và tập hợp",
    _H + "he_thuc_luong_tam_giac": "Chương III. Hệ thức lượng trong tam giác",
    _H + "vecto_mat_phang": "Chương IV. Vectơ",
    _T + "thong_ke_khong_ghep_nhom": "Chương V. Các số đặc trưng của mẫu số liệu không ghép nhóm",
    _H + "toa_do_mat_phang": "Chương VII. Phương pháp toạ độ trong mặt phẳng",
    _D + "gioi_han_ham_lien_tuc": "Chương V. Giới hạn. Hàm số liên tục",
    _D + "ung_dung_dao_ham": "Chương I. Ứng dụng đạo hàm để khảo sát và vẽ đồ thị hàm số",
    _H + "vecto_khong_gian": "Chương II. Vectơ và hệ trục toạ độ trong không gian",
    _T + "thong_ke_phan_tan": "Chương III. Các số đặc trưng đo mức độ phân tán của mẫu số liệu ghép nhóm",
    _D + "nguyen_ham_tich_phan": "Chương IV. Nguyên hàm và tích phân",
    _H + "toa_do_khong_gian": "Chương V. Phương pháp toạ độ trong không gian",
    _T + "xac_suat_co_dieu_kien": "Chương VI. Xác suất có điều kiện",
}
OLD_TO_NEW = {
    _D + "bat_phuong_trinh_bac_nhat_hai_an": _D + "he_bat_phuong_trinh_bac_nhat_hai_an",
    _D + "cap_so_cong": _D + "day_so_cap_so",
    _D + "cap_so_nhan": _D + "day_so_cap_so",
    _D + "dao_ham": _D + "dao_ham",
    # Two targets: main one ung_dung_dao_ham (2026-III-4, golden set); 2025-III-2 is ham_so_bac_hai, see _ALSO.
    _D + "ham_so_thuc_te": _D + "ung_dung_dao_ham",
    _D + "he_bat_phuong_trinh": _D + "he_bat_phuong_trinh_bac_nhat_hai_an",
    _D + "he_phuong_trinh_bac_nhat": _D + "he_phuong_trinh_bac_nhat_ba_an",
    _D + "nguyen_ham": _D + "nguyen_ham_tich_phan",
    _D + "nguyen_ham_mo_hinh": _D + "nguyen_ham_tich_phan",
    _D + "phuong_trinh_logarit": _D + "mu_logarit",
    _D + "phuong_trinh_luong_giac": _D + "luong_giac",
    _D + "the_tich_khoi_tron_xoay": _D + "nguyen_ham_tich_phan",
    _D + "tich_phan_dien_tich": _D + "nguyen_ham_tich_phan",
    _D + "tich_phan_thuc_te": _D + "nguyen_ham_tich_phan",
    _D + "tiem_can": _D + "ung_dung_dao_ham",
    _D + "ung_dung_dao_ham": _D + "ung_dung_dao_ham",
    _H + "khoang_cach": _H + "quan_he_vuong_goc",
    _H + "quan_he_song_song": _H + "quan_he_song_song",
    _H + "the_tich": _H + "quan_he_vuong_goc",
    _H + "the_tich_thuc_te": _D + "nguyen_ham_tich_phan",  # strand changes: spherical-cap volume needs an integral
    _H + "toa_do_duong_thang": _H + "toa_do_khong_gian",
    _H + "toa_do_mat_phang": _H + "toa_do_khong_gian",
    _H + "toa_do_ung_dung": _H + "toa_do_khong_gian",
    _H + "toa_do_vecto": _H + "vecto_khong_gian",  # vector coordinates are Toán 12 Chương II
    _H + "vecto_khong_gian": _H + "vecto_khong_gian",
    _T + "bien_co_doc_lap": _T + "xac_suat_quy_tac",
    _T + "to_hop": _D + "to_hop",  # strand changes: CT GDPT 2018 puts combinatorics under algebra
    _T + "trung_vi_ghep_nhom": _T + "thong_ke_trung_tam",
    _T + "tu_phan_vi_ghep_nhom": _T + "thong_ke_trung_tam",
    _T + "xac_suat_co_dien": _T + "xac_suat_co_dien",
    _T + "xac_suat_co_dieu_kien": _T + "xac_suat_co_dieu_kien",
}
_ALSO = {_D + "ham_so_thuc_te": _D + "ham_so_bac_hai"}  # second target, only for retrieval


def old_codes(topic):
    """Old exam_item codes stored in Qdrant that belong to the new `topic`."""
    return [old for old, new in OLD_TO_NEW.items() if topic in (new, _ALSO.get(old))]

# Vietnamese search phrase per topic code: retrieval queries by it, generation names the topic with it (T-026, T-036).
TOPIC_QUERIES = json.loads((Path(__file__).parent / "storage" / "topic_queries.json").read_text(encoding="utf-8"))
