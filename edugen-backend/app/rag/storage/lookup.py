"""Tóm tắt: tra cứu đoạn tài liệu theo ID trích dẫn (T-029) để màn hình duyệt đề của Backend hiển thị câu hỏi lấy từ đâu (tiêu đề, trang, nội dung, nguồn); ID không có trong chỉ mục được trả về trong danh sách thiếu, không báo lỗi."""

from app.rag.storage.qdrant import COLLECTION, default_client, point_id


def make_chunk_lookup(client=None):
    """-> lookup(ids) -> (found {id: chunk dict}, missing [id]); default: the same local client as make_generator()."""
    if client is None:
        client = default_client()

    def lookup(ids):
        if not client.collection_exists(COLLECTION):  # nothing ingested yet
            return {}, list(ids)
        points = client.retrieve(COLLECTION, [point_id(i) for i in ids])
        found = {p.payload["id"]: p.payload for p in points}
        return found, [i for i in ids if i not in found]

    return lookup
