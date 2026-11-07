"""Tóm tắt: BUG-004: chuẩn hoá LaTeX của câu sinh ra: dấu `\\` đứng trước ký tự Unicode (≤, ≥, ≈, ≠, ⇔...) hoặc lệnh hỏng
(`\\tiff`, `\\℔`) đổi về lệnh LaTeX đúng; chuỗi đã đúng giữ nguyên. Dùng chung cho câu mới sinh và lúc xuất Word."""

import pytest

from app.rag.generation.latex import normalize_latex


@pytest.mark.parametrize("raw, fixed", [
    (r"$1 \≤ x \≤ 120$", r"$1 \le x \le 120$"),  # e81f6617 Q17
    (r"$x \≥ 1$", r"$x \ge 1$"),  # Q18
    (r"$a \≈ 7,07$", r"$a \approx 7,07$"),
    (r"$a \≠ b$", r"$a \ne b$"),
    (r"$y'=0 \⇔ x=1$", r"$y'=0 \iff x=1$"),
    (r"$y'=0 \℔ x=1$", r"$y'=0 \iff x=1$"),  # lời giải Q18, Q19
    (r"$f'(x)=0 \tiff x=2$", r"$f'(x)=0 \iff x=2$"),  # lời giải Q1
    (r"$\tiff$", r"$\iff$"),
    (r"$x \∈ \mathbb{R}$", r"$x \in \mathbb{R}$"),
    (r"$\π r^2$", r"$\pi r^2$"),
])
def test_BUG_004_backslash_before_unicode_or_a_broken_command_is_fixed(raw, fixed):
    assert normalize_latex(raw) == fixed


@pytest.mark.parametrize("ok", [
    r"$1 \le x \le 120$", r"$\frac{1}{2}\times 3 \neq \sqrt{2}$", r"$\text{tiền}$", r"$\tan x$", r"$\theta$",
    "Cho hàm số $y=x^3$ có đồ thị (C).", r"$x ≤ 2$",  # a bare Unicode symbol (no backslash) is valid
])
def test_correct_latex_and_plain_text_are_unchanged(ok):
    assert normalize_latex(ok) == ok


def test_unknown_unicode_after_a_backslash_keeps_the_symbol_without_the_backslash():
    assert normalize_latex(r"$a \⊥ b$") == r"$a ⊥ b$"


def test_control_characters_from_json_escapes_are_made_visible_again():
    """repair_latex_escapes keeps `\b`/`\f` before a non-letter as JSON escapes, so the text holds backspace or form
    feed; Word (XML) rejects them and the answer-key export crashed (exam e51bd843, câu 6: "P(A) \x085 P(B)")."""
    assert normalize_latex("$P(A) \x085 P(B)$") == r"$P(A) \b5 P(B)$"
    assert normalize_latex("a\x0c1") == r"a\f1"
    assert normalize_latex("x\x00y\x1bz") == "xyz"  # no visible spelling: dropped
    assert normalize_latex("dòng 1\ndòng 2\tcột") == "dòng 1\ndòng 2\tcột"  # valid in XML, kept
