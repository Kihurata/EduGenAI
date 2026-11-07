"""Tóm tắt: nạp theo danh mục nguồn data/sources.yaml (T-035, bước 1 của D-009): mỗi nguồn có id, doc_type, file, subject, grade, official, confidence (đề thi thêm exam_kind, year); nạp chọn bộ cắt theo doc_type, payload có source_id; nạp lại bằng danh mục giữ nguyên id, số lượng và nội dung đoạn so với nạp theo file."""

from pathlib import Path

import pytest
import yaml

from app.rag.ingest import ingest
from app.rag.manifest import MANIFEST, ingest_sources, load_sources
from app.rag.storage.qdrant import COLLECTION
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import EXAM_2025, count_words, memory_client, sgk_pages_md, words

LESSONS = [("Chương I. Ứng dụng đạo hàm", "Bài 1. Tính đơn điệu", [("1. Tính đơn điệu", words(200, "a"))])]


def _manifest(tmp_path, sources):
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump({"sources": sources}, allow_unicode=True), encoding="utf-8")
    return path


def _sgk_entry(tmp_path, **over):
    sgk_pages_md(tmp_path / "parsed" / "sgk-toan-12-tap-1" / "normalized" / "pages.md", LESSONS)
    return {"id": "sgk-toan-12-tap-1", "doc_type": "sgk", "file": "parsed/sgk-toan-12-tap-1/normalized/pages.md",
            "subject": "toan", "grade": 12, "official": True, "confidence": "high"} | over


def _exam_entry(**over):
    return {"id": "tn-2025-0101", "doc_type": "exam", "file": str(EXAM_2025), "subject": "toan", "grade": 12,
            "official": True, "confidence": "high", "exam_kind": "tot_nghiep", "year": 2025} | over


def _points(client):
    return {p.payload["id"]: p.payload for p in client.scroll(COLLECTION, limit=10_000)[0]}


def test_every_chunk_carries_its_source_id(tmp_path):
    client = memory_client()

    ingest_sources(_manifest(tmp_path, [_sgk_entry(tmp_path), _exam_entry()]), client, FakeEmbedder(),
                   count_tokens=count_words)

    by_kind = {}
    for p in _points(client).values():
        by_kind.setdefault(p["kind"], set()).add(p["source_id"])
    assert by_kind.pop("exam_item") == {"tn-2025-0101"}
    assert set().union(*by_kind.values()) == {"sgk-toan-12-tap-1"}


def test_manifest_ingest_keeps_ids_count_and_text_of_file_ingest(tmp_path):
    entries = [_sgk_entry(tmp_path), _exam_entry()]
    by_file, by_manifest = memory_client(), memory_client()

    ingest([tmp_path / entries[0]["file"], EXAM_2025], by_file, FakeEmbedder(), count_tokens=count_words)
    ingest_sources(_manifest(tmp_path, entries), by_manifest, FakeEmbedder(), count_tokens=count_words)

    old, new = _points(by_file), _points(by_manifest)
    assert new.keys() == old.keys()
    assert {i: p["text"] for i, p in new.items()} == {i: p["text"] for i, p in old.items()}


def test_official_and_grade_come_from_the_manifest(tmp_path):
    client = memory_client()

    ingest_sources(_manifest(tmp_path, [_exam_entry(official=False, grade=11)]), client, FakeEmbedder())

    assert {(p["official"], p["grade"]) for p in _points(client).values()} == {(False, 11)}


def test_sgk_text_and_heading_path_carry_the_manifest_grade(tmp_path):
    """T-056: a grade-11 book must not read "Toán 12 > ..." in the embedded text or the citation path."""
    client = memory_client()

    ingest_sources(_manifest(tmp_path, [_sgk_entry(tmp_path, grade=11)]), client, FakeEmbedder(),
                   count_tokens=count_words)

    points = _points(client).values()
    assert points
    assert {p["heading_path"].split(" > ")[0] for p in points} == {"Toán 11"}
    assert all(p["text"].startswith("Toán 11 > ") for p in points)


def test_sgk_subject_comes_from_the_manifest(tmp_path):
    """T-064: a Hóa book must be filtered as `hoa` and read "Hoá học 12 > ...", not be stored as Toán."""
    client = memory_client()

    ingest_sources(_manifest(tmp_path, [_sgk_entry(tmp_path, subject="hoa")]), client, FakeEmbedder(),
                   count_tokens=count_words)

    points = _points(client).values()
    assert points
    assert {p["subject"] for p in points} == {"hoa"}
    assert {p["heading_path"].split(" > ")[0] for p in points} == {"Hoá học 12"}
    assert all(p["text"].startswith("Hoá học 12 > ") for p in points)


@pytest.mark.parametrize("entry, error", [
    ({"id": "x"}, "x: missing doc_type"),
    ({"doc_type": "video"}, "unknown doc_type 'video'"),
    ({"exam_kind": None}, "tn-2025-0101: missing exam_kind"),
    ({"year": None}, "tn-2025-0101: missing year"),
    ({"exam_kind": "official"}, "tn-2025-0101: unknown exam_kind 'official'"),  # D-017: origin lives in `official`
])
def test_a_bad_entry_is_refused_before_anything_is_ingested(tmp_path, entry, error):
    bad = {k: v for k, v in (_exam_entry() | entry).items() if v is not None}
    if "id" in entry:
        bad = {"id": "x"}

    with pytest.raises(ValueError, match=error):
        load_sources(_manifest(tmp_path, [bad]))


def test_duplicate_source_ids_are_refused(tmp_path):
    with pytest.raises(ValueError, match="duplicate source id tn-2025-0101"):
        load_sources(_manifest(tmp_path, [_exam_entry(), _exam_entry()]))


def test_the_repo_manifest_is_valid_and_its_exam_files_exist():
    sources = load_sources(MANIFEST)

    exams = [s for s in sources if s["doc_type"] == "exam"]
    assert len(exams) == 7  # 3 grade-12 graduation exams + 4 grade 10-11 periodic exams (T-034 re-ingest)
    assert all((Path(MANIFEST).parent / s["file"]).exists() for s in exams)
    # D-017: one value set by exam format; the 3 Bộ exams (official + reference) are tot_nghiep
    assert sorted(s["exam_kind"] for s in exams) == ["dinh_ky_7991"] * 4 + ["tot_nghiep"] * 3


def test_exam_kind_comes_from_the_manifest(tmp_path):
    client = memory_client()

    ingest_sources(_manifest(tmp_path, [_exam_entry(exam_kind="dinh_ky_7991")]), client, FakeEmbedder())

    assert {p["exam_kind"] for p in _points(client).values()} == {"dinh_ky_7991"}
