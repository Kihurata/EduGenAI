"""Tóm tắt: truy xuất theo ô ma trận (T-006): lọc Qdrant theo môn/bài (lý thuyết) và chủ đề (câu đề mẫu; mã chủ đề mới cũng khớp các mã cũ trong chỉ mục), ô không có câu hỏi thì tìm bằng câu tiếng Việt của chủ đề trong topic_queries.json (T-026; chủ đề không có trong bảng thì báo lỗi), ô mức Vận dụng lấy thêm tối đa 2 đoạn bài tập SGK (kind exercise) sau lý thuyết, làm mẫu độ khó; rồi xếp hạng bằng tìm kiếm lai dense + sparse (RRF) hoặc chỉ dense; trả về hai danh sách riêng. Ô có lớp (grade) thì chỉ lấy lý thuyết của lớp đó; exclude_year bỏ câu đề của năm đó để tránh lộ đề (T-036). Cô lập trường (RBAC): chỉ trả đoạn dùng chung và đoạn của trường trong ô; ô không có school_id chỉ thấy đoạn dùng chung; trong trường, đề mẫu GV tự tải (teacher_id) chỉ GV đó thấy. Câu đề mẫu lọc theo dạng câu (type); mức độ của ô và loại đề (exam_kind: tot_nghiep | dinh_ky_7991, D-017) chỉ là ưu tiên: thiếu thì bù cho đủ k, bỏ mức độ trước rồi đến loại đề (T-034); trong cùng một lượt câu official đứng trước. example_pool của ô (all mặc định | official | unofficial) chọn câu đề mẫu chỉ từ đề chính thức, chỉ từ đề không chính thức, hoặc cả hai."""

from qdrant_client import models

from app.rag.dto import Cell, Chunk, Retrieved, Vector
from app.rag.embedding import Embedder
from app.rag.storage.qdrant import COLLECTION, sparse_vector
from app.rag.vocab import CHAPTER_BY_TOPIC, PART_BY_TYPE, TOPIC_QUERIES, old_codes

EXAMPLE_POOLS = {"all": None, "official": True, "unofficial": False}  # example_pool -> official filter (None = no filter)
EXERCISES = 2  # SGK exercise chunks added for a Vận dụng cell (~1,700 characters each)


def retrieve(client, embedder: Embedder, cell: Cell, k=5, mode="hybrid", exclude_year=None) -> Retrieved:
    """cell: {"subject", "topic", "type", optional "lesson", "grade", "query"} -> (theory_chunks, exam_items)."""
    query = cell.get("query") or _topic_query(cell["topic"])
    vec = embedder.embed_query(query)
    scope = _school_scope(cell.get("school_id"), cell.get("teacher_id"))
    sgk = {"subject": cell["subject"], "lesson": cell.get("lesson"), "grade": cell.get("grade")}
    chapter = {"chapter": CHAPTER_BY_TOPIC.get(cell["topic"])}  # D-021: a preference, topped up by grade when short
    theory = _search_preferring(client, vec, _filter(scope, kind="theory", **sgk), chapter, k, mode)
    if cell.get("level") == "Vận dụng":  # SGK exercises show the difficulty; Vận dụng cells came out too easy (T-036)
        theory += _search_preferring(client, vec, _filter(scope, kind="exercise", **sgk), chapter, EXERCISES, mode)
    topics = [cell["topic"], *old_codes(cell["topic"])]  # the index still stores the old lesson-level codes
    # Not filtered by grade: grade-12 exams test grade 10-11 topics too, and grade 10-11 school exams are examples for them (D-009 amendment).
    if cell["type"] not in PART_BY_TYPE:  # fail loudly: a typo would otherwise just find no exam items
        raise KeyError(f"unknown question type {cell['type']!r}")
    pool = cell.get("example_pool") or "all"
    if pool not in EXAMPLE_POOLS:  # fail loudly: a typo would otherwise silently fall back to every item
        raise ValueError(f"unknown example_pool {pool!r}; use one of {', '.join(EXAMPLE_POOLS)}")
    exam_filter = _filter(scope, kind="exam_item", subject=cell["subject"], topic=topics, type=cell["type"],
                          official=EXAMPLE_POOLS[pool])
    if exclude_year is not None:
        exam_filter.must_not = [models.FieldCondition(key="year", match=models.MatchValue(value=exclude_year))]
    # T-034: preferences, not filters; listed so that level is dropped first, then exam_kind.
    preferences = {"exam_kind": cell.get("exam_kind"), "level": cell.get("level")}
    exam_items = _search_preferring(client, vec, exam_filter, preferences, k, mode)
    return Retrieved(theory, exam_items)


def _search_preferring(client, vec, flt, preferences, k, mode) -> list[Chunk]:
    """Search with every preference, then top up to k dropping the last one each pass; first hits stay first.
    Within a pass official items go first (D-017); sorted here because `official` has no payload index on the cluster."""
    prefs = [(key, value) for key, value in preferences.items() if value]
    found = {}
    for n in range(len(prefs), -1, -1):
        narrowed = models.Filter(must=[*flt.must, *_conditions(**dict(prefs[:n]))], must_not=flt.must_not)
        for c in sorted(_search(client, vec, narrowed, k, mode), key=lambda c: not c.official):
            found.setdefault(c.id, c)
        if len(found) >= k:
            break
    return list(found.values())[:k]


def _topic_query(topic):
    if not TOPIC_QUERIES.get(topic):
        # No fallback to the raw label: it retrieves the wrong lesson silently (T-026).
        raise ValueError(f"no search phrase for topic {topic!r} in rag/storage/topic_queries.json")
    return TOPIC_QUERIES[topic]


def _school_scope(school_id, teacher_id=None):
    """RBAC: shared chunks (no school_id; old points lack the key) plus the cell's own school; no school = shared only.
    Inside the school, a teacher's own uploads (teacher_id) are seen only by that teacher; no teacher_id = whole school."""
    shared = models.IsEmptyCondition(is_empty=models.PayloadField(key="school_id"))
    if not school_id:
        return shared
    whole_school = models.IsEmptyCondition(is_empty=models.PayloadField(key="teacher_id"))
    mine = [whole_school] + ([models.FieldCondition(key="teacher_id", match=models.MatchValue(value=teacher_id))]
                             if teacher_id else [])
    school = models.Filter(must=[models.FieldCondition(key="school_id", match=models.MatchValue(value=school_id))],
                           should=mine)
    return models.Filter(should=[shared, school])


def _filter(*conditions, **fields):
    return models.Filter(must=[*conditions, *_conditions(**fields)])


def _conditions(**fields):
    """One match per field; a list matches any of its values, None means no condition."""
    return [models.FieldCondition(key=key, match=models.MatchAny(any=value) if isinstance(value, list)
                                  else models.MatchValue(value=value))
            for key, value in fields.items() if value is not None]


def _search(client, vec: Vector, flt, k, mode) -> list[Chunk]:
    if mode not in _SEARCHES:
        raise ValueError(f"unknown search mode {mode!r}; use one of {sorted(_SEARCHES)}")
    return [Chunk.from_dict(p.payload) for p in _SEARCHES[mode](client, vec, flt, k)]


def _dense(client, vec, flt, k):
    return client.query_points(COLLECTION, query=vec.dense, using="dense", query_filter=flt, limit=k).points


def _hybrid(client, vec, flt, k):
    """Dense and sparse top 4k, fused with reciprocal rank fusion (D-004)."""
    dense = models.Prefetch(query=vec.dense, using="dense", filter=flt, limit=k * 4)
    sparse = models.Prefetch(query=sparse_vector(vec), using="sparse", filter=flt, limit=k * 4)
    return client.query_points(COLLECTION, prefetch=[dense, sparse], query=models.FusionQuery(fusion=models.Fusion.RRF),
                               query_filter=flt, limit=k).points


_SEARCHES = {"hybrid": _hybrid, "dense": _dense}
