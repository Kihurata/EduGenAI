"""Lưu file (ma trận gốc, đề mẫu, DOCX xuất ra) theo khóa tương đối.

Hiện lưu ở thư mục storage/ trên đĩa; sau này đổi sang S3/MinIO chỉ cần cùng các hàm này.
"""

from pathlib import Path, PurePosixPath

from app.core.config import settings


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def path(self, key: str) -> Path:
        parts = PurePosixPath(key).parts
        if not key or key.startswith(("/", "\\")) or ".." in parts:
            raise ValueError(f"Khóa lưu trữ không hợp lệ: {key!r}")
        return self.root.joinpath(*parts)

    def save(self, key: str, data: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    """Dependency cho FastAPI; test override để lưu vào thư mục tạm."""
    return LocalStorage(settings.storage_dir)
