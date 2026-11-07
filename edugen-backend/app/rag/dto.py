"""Tóm tắt: các kiểu dữ liệu (DTO) mà các bước của RAG trao cho nhau: cắt đoạn → nhúng → lưu/truy xuất → sinh câu → kiểm tra.

Flow and who hands what to whom:

    chunking  ──Chunk──►  embedding  ──Vector──►  storage
    storage   ──Retrieved(theory, exam_items)──►  generation  ──Question──►  checking
    checking  ──errors [str] (+ Verification)──►  pipeline  ──GenerationResult(valid, rejected)──►  Backend

- Internal hand-offs are frozen dataclasses / NamedTuples (NamedTuples still unpack: `theory, items = retrieve(...)`).
- `Cell`, `Question`, `Rejected` are the JSON contract with the Backend (D-008), so they stay plain dicts;
  the TypedDicts only document their keys. Change them only through a new D-### decision.
"""

from dataclasses import asdict, dataclass, fields
from typing import Literal, NamedTuple, NotRequired, TypedDict

EXAM_ONLY = ("year", "exam_code", "part", "question_no", "topic", "type", "exam_kind", "level", "statement_levels")


# chunking → embedding / storage (D-003)
@dataclass
class Chunk:
    id: str
    kind: str  # theory | exercise | exam_item
    text: str
    subject: str
    grade: int
    chapter: str
    lesson: str
    section: str
    heading_path: str
    source: str
    page: int | None
    official: bool
    # exam_item only
    year: int | None = None
    exam_code: str | None = None
    part: str | None = None
    question_no: int | None = None
    topic: str | None = None
    type: str | None = None  # multiple_choice | true_false | short_answer (T-034)
    exam_kind: str | None = None  # tot_nghiep | dinh_ky_7991 from data/sources.yaml (D-017)
    level: str | None = None  # Biết | Hiểu | Vận dụng, when the source says
    statement_levels: list[str] | None = None  # true_false, a → d
    school_id: str | None = None  # uploading school; None = shared (SGK, official exams)
    teacher_id: str | None = None  # uploading teacher; None = the whole school (admin upload) or shared
    source_id: str | None = None  # id in data/sources.yaml (T-035); None for files ingested without the manifest

    @classmethod
    def from_dict(cls, d):
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})

    def to_dict(self):
        d = asdict(self)
        if self.kind != "exam_item":
            for k in EXAM_ONLY:
                del d[k]
        if self.source_id is None:
            del d["source_id"]  # files ingested without the manifest keep the pre-T-035 payload
        if self.school_id is None:
            del d["school_id"]  # shared chunks keep the pre-RBAC payload, same as points already indexed
        if self.teacher_id is None:
            del d["teacher_id"]
        return d


# embedding → storage
@dataclass(frozen=True)
class Vector:
    dense: list[float]  # 1024 floats (bge-m3)
    sparse: dict[int, float]  # token id → weight


# storage → generation
class Retrieved(NamedTuple):
    theory: list[Chunk]  # what to ask about (SGK)
    exam_items: list[Chunk]  # how to ask it (official exam items of the same part)


# Backend → RAG (D-008)
class Cell(TypedDict):
    subject: str
    topic: str  # topic code from rag.vocab.TOPICS
    level: str
    type: Literal["multiple_choice", "true_false", "short_answer"]
    count: int
    statement_levels: NotRequired[list[str]]
    content_unit: NotRequired[str]  # unit of the matrix row, for the prompt only (not a retrieval filter)
    statement_units: NotRequired[list[str | None]]  # true_false: unit of statements a → d, for the prompt
    lesson: NotRequired[str]
    query: NotRequired[str]
    school_id: NotRequired[str]
    teacher_id: NotRequired[str]  # the teacher generating: sees own sample exams too
    exam_kind: NotRequired[str]  # T-034/D-017: preferred kind of example exam, tot_nghiep | dinh_ky_7991
    example_pool: NotRequired[str]  # all (default) | official | unofficial: which exam items may be examples
    previous_stems: NotRequired[list[str]]  # BUG-005: stems already in the exam; repeats are rejected


# generation → checking → Backend (D-008)
class Question(TypedDict):
    type: str
    stem: str
    explanation: str
    level: str
    topic: str
    source_chunk_ids: list[str]
    options: NotRequired[dict[str, str]]  # multiple_choice
    statements: NotRequired[list[dict]]  # true_false: [{label, text, answer, explanation, level?}]
    answer: NotRequired[str]  # multiple_choice, short_answer
    figure: NotRequired[str]
    table: NotRequired[list[list[str]]]
    figure_spec: NotRequired[dict]  # {solid, a, b, h, foot}: sizes of a solid the backend draws (domain/figure.py)
    sympy: NotRequired[dict]  # {"expr": str, "verified": bool}


class Rejected(TypedDict):
    question: Question
    errors: list[str]


# checking: result of recomputing one answer with SymPy
@dataclass(frozen=True)
class Verification:
    status: Literal["verified", "mismatch", "unverifiable"]
    answer: str | None
    value: str | None  # SymPy's value, rounded like the answer
    reason: str | None = None


# pipeline → Backend
class GenerationResult(NamedTuple):
    valid: list[Question]
    rejected: list[Rejected]
