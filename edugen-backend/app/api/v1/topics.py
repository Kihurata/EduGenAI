"""Danh sách chủ đề của một môn cho dropdown khi GV duyệt đề mẫu (T-050, D-013)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.domain.topics import topic_grade, topics_for

router = APIRouter(prefix="/topics", tags=["topics"])


class TopicOut(BaseModel):
    code: str  # mã RAG "<mạch hoặc môn>/<chương>", ghi vào trường topic của câu
    name: str
    grade: int


@router.get("")
def list_topics(subject: Annotated[str, Query(min_length=1)], user: CurrentUser) -> list[TopicOut]:
    topics = topics_for(subject)
    if not topics:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Môn '{subject}' chưa có danh sách chủ đề")
    return [TopicOut(code=f"{t.strand}/{t.code}", name=t.name, grade=topic_grade(t, 12)) for t in topics]
