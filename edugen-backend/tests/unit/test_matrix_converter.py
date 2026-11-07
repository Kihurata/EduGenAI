"""Adapter marker: ảnh/PDF ma trận → markdown. Không bao giờ chạy marker thật trong test.

Đầu ra mong muốn:
- Gọi marker_single với marker_config.json và thư mục output tạm, đọc file .md nó sinh ra.
- Biến trong .env (GOOGLE_API_KEY, SURYA_INFERENCE_BACKEND...) được truyền cho marker.
- Marker lỗi, quá giờ, chưa cài hoặc không sinh .md → ConversionError tiếng Việt.
"""

import subprocess
from pathlib import Path

import pytest

from app.services.matrix_converter import ConversionError, MarkerConverter


class FakeRun:
    def __init__(self, returncode=0, markdown="# ma trận", stderr="", raises=None):
        self.returncode, self.markdown, self.stderr, self.raises = returncode, markdown, stderr, raises
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.raises:
            raise self.raises
        out = Path(cmd[cmd.index("--output_dir") + 1])
        if self.markdown is not None:
            (out / "anh").mkdir(parents=True)
            (out / "anh" / "anh.md").write_text(self.markdown, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, self.returncode, "", self.stderr)


def converter(run, tmp_path) -> MarkerConverter:
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=khoa\nSURYA_INFERENCE_BACKEND=llamacpp\n", encoding="utf-8")
    return MarkerConverter("marker_config.json", env_file=env_file, run=run)


def test_runs_marker_with_config_and_returns_markdown(tmp_path):
    run = FakeRun(markdown="<table></table>")
    source = tmp_path / "anh.png"
    assert converter(run, tmp_path).convert(source) == "<table></table>"
    [(cmd, kwargs)] = run.calls
    assert cmd[:4] == ["marker_single", str(source), "--config_json", "marker_config.json"]
    assert kwargs["env"]["GOOGLE_API_KEY"] == "khoa"
    assert kwargs["env"]["SURYA_INFERENCE_BACKEND"] == "llamacpp"
    assert kwargs["timeout"] > 0


@pytest.mark.parametrize(
    "run, message",
    [
        (FakeRun(returncode=1, stderr="CUDA hỏng"), "CUDA hỏng"),
        (FakeRun(raises=subprocess.TimeoutExpired("marker_single", 1)), "quá thời gian"),
        (FakeRun(raises=FileNotFoundError()), "chưa cài marker"),
        (FakeRun(markdown=None), "không sinh"),
    ],
)
def test_failures_become_conversion_errors(tmp_path, run, message):
    with pytest.raises(ConversionError, match=message):
        converter(run, tmp_path).convert(tmp_path / "anh.png")
