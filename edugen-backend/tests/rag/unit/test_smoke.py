"""Tóm tắt: test khói, đảm bảo pytest chạy được và gói rag import được."""


def test_rag_package_imports():
    import app.rag

    assert app.rag.__name__ == "app.rag"
