"""Tóm tắt: chuẩn hoá LaTeX của câu sinh ra (BUG-004): model đôi khi viết `\\` rồi một ký tự Unicode (`\\≤`, `\\≥`) hoặc
một lệnh hỏng (`\\tiff`, `\\℔`); đổi về lệnh LaTeX đúng (`\\le`, `\\ge`, `\\iff`). Ký tự Unicode lạ sau `\\` thì chỉ bỏ dấu
`\\` (ký tự đứng một mình vẫn hiển thị được). Dùng cho câu mới sinh (generate) và lúc xuất Word (đề đã lưu trước bản sửa)."""

import re

# Unicode symbol the model put after a backslash -> the LaTeX command it meant.
_UNICODE_COMMANDS = {
    "≤": "le", "≥": "ge", "≠": "ne", "≈": "approx", "±": "pm", "×": "times", "÷": "div", "·": "cdot",
    "∈": "in", "∉": "notin", "⊂": "subset", "⊆": "subseteq", "∪": "cup", "∩": "cap", "∅": "emptyset",
    "∞": "infty", "→": "to", "⇒": "Rightarrow", "⇔": "iff", "↔": "leftrightarrow", "∀": "forall", "∃": "exists",
    "√": "sqrt", "∫": "int", "∑": "sum", "π": "pi", "α": "alpha", "β": "beta", "γ": "gamma", "Δ": "Delta",
    "θ": "theta", "λ": "lambda", "μ": "mu", "σ": "sigma", "φ": "varphi", "ω": "omega", "°": "circ",
    "℔": "iff",  # e81f6617 Q18/Q19: "℔" stood where the solution meant ⇔
}
# Broken commands seen in generated text: \tiff is \iff behind a stray "t" (a tab escape gone wrong, e81f6617 Q1).
_BROKEN_COMMANDS = {"tiff": "iff"}

_UNICODE_AFTER_BACKSLASH = re.compile(r"\\([^\x00-\x7f])")
_BROKEN = re.compile(r"\\(" + "|".join(_BROKEN_COMMANDS) + r")(?![a-zA-Z])")


def normalize_latex(text: str) -> str:
    def unicode_command(m):
        command = _UNICODE_COMMANDS.get(m.group(1))
        if command is None:
            return m.group(1)  # unknown symbol: the bare Unicode character still renders
        follows_letter = m.end() < len(m.string) and m.string[m.end()].isalpha()
        return f"\\{command}" + (" " if follows_letter else "")  # "\≤x" -> "\le x", not "\lex"

    text = _UNICODE_AFTER_BACKSLASH.sub(unicode_command, text)
    return _BROKEN.sub(lambda m: f"\\{_BROKEN_COMMANDS[m.group(1)]}", text)


def normalize_strings(value):
    """normalize_latex on every string of a question (stem, options, statements, explanation, answer...)."""
    if isinstance(value, str):
        return normalize_latex(value)
    if isinstance(value, list):
        return [normalize_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_strings(v) for k, v in value.items()}
    return value
