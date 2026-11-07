"""Lưu file ở thư mục storage/ trên đĩa, theo khóa tương đối."""

import pytest

from app.services.storage import LocalStorage


def test_save_read_delete(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.save("matrices/abc/source.png", b"png")
    assert storage.read("matrices/abc/source.png") == b"png"
    assert storage.path("matrices/abc/source.png") == tmp_path / "matrices" / "abc" / "source.png"
    storage.delete("matrices/abc/source.png")
    assert not storage.path("matrices/abc/source.png").exists()
    storage.delete("matrices/abc/source.png")  # xóa file không còn thì bỏ qua


@pytest.mark.parametrize("key", ["../ngoai.txt", "/tuyet_doi.txt", "a/../../b", ""])
def test_keys_cannot_escape_the_storage_root(tmp_path, key):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).save(key, b"x")
