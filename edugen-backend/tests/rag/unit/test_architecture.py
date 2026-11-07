"""Tóm tắt: giữ đúng hướng phụ thuộc giữa các bước của RAG: mỗi bước chỉ dùng DTO (và từ vựng chung), không gọi pipeline hay bước khác."""

import ast
from pathlib import Path

RAG = Path(__file__).parents[3] / "app" / "rag"

# stage -> app.rag modules it may import (besides itself). Only pipeline.py / ingest.py wire stages together.
ALLOWED = {
    "chunking": {"dto"},
    "embedding": {"dto"},
    "storage": {"dto", "embedding", "vocab"},  # embedding: only the Embedder protocol
    "generation": {"dto", "vocab"},
    "checking": {"dto"},
}


def rag_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
    names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    return {name.split(".")[2] for name in names if name.startswith("app.rag.")}


def test_stages_depend_only_on_dtos_and_shared_vocabulary():
    broken = []
    for stage, allowed in ALLOWED.items():
        for path in (RAG / stage).glob("*.py"):
            broken += [f"{stage}/{path.name} imports app.rag.{m}" for m in rag_imports(path) - allowed - {stage}]
    assert broken == []


def test_dto_module_depends_on_no_stage():
    assert rag_imports(RAG / "dto.py") == set()
