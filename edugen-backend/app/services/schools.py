"""Xoá trường (T-046): Postgres tự xoá dữ liệu của trường theo ON DELETE CASCADE, Qdrant thì không, nên xoá đoạn Qdrant của trường trước; RAG lỗi thì trường còn nguyên để xoá lại."""

from sqlalchemy.orm import Session

from app.models import School
from app.services.rag_ingest import RagDeleter


def delete_school(db: Session, school: School, rag: RagDeleter) -> None:
    rag.delete(str(school.id))
    db.delete(school)
    db.commit()
