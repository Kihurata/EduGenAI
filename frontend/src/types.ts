// Khớp schema OpenAPI của BE (edugen-backend, /api/v1).

export type UserRole = "teacher" | "admin";
export type QuestionType = "multiple_choice" | "true_false" | "short_answer";
export type Level = "Biết" | "Hiểu" | "Vận dụng";
export type MatrixStatus = "uploaded" | "converting" | "parsed" | "invalid" | "confirmed" | "failed";
export type ExamStatus = "generating" | "generated" | "incomplete" | "failed" | "approved";
export type CellRunStatus = "complete" | "short" | "error";
export type IngestStatus = "pending" | "needs_review" | "sent" | "ingested" | "failed";
export type ExportVariant = "student" | "teacher";

export const QUESTION_TYPES: QuestionType[] = ["multiple_choice", "true_false", "short_answer"];
export const LEVELS: Level[] = ["Biết", "Hiểu", "Vận dụng"];
export const TYPE_LABEL: Record<QuestionType, string> = {
  multiple_choice: "Nhiều lựa chọn",
  true_false: "Đúng/Sai",
  short_answer: "Trả lời ngắn",
};
export const PART_OF_TYPE: Record<QuestionType, string> = {
  multiple_choice: "I",
  true_false: "II",
  short_answer: "III",
};

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  school: { id: string; code: string; name: string };
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Accepted {
  id: string;
  status: string;
}

export interface Issue {
  message: string;
  location: string | null;
}

export interface CellIn {
  topic: string;
  content_unit: string | null;
  type: QuestionType;
  level: Level;
  count: number;
  statement_levels: Level[] | null;
  /** Đúng–Sai only: content unit of statements a–d (one question may span several units); null = content_unit. */
  statement_units: (string | null)[] | null;
  competency_codes: string[];
}

export interface Cell extends CellIn {
  id: string;
  sort_order: number;
}

export interface MatrixSummary {
  id: string;
  status: MatrixStatus;
  subject: string | null;
  grade: number | null;
  name: string | null;
  source_filename: string;
  created_at: string;
}

export interface Matrix extends MatrixSummary {
  issues: Issue[];
  error_message: string | null;
  confirmed_at: string | null;
  cells: Cell[];
}

export interface Statement {
  text: string;
  correct: boolean;
  explanation: string;
}

// Câu hỏi theo format của BE (app/domain/question.py).
export interface QuestionContent {
  type: QuestionType;
  level: Level;
  stem: string;
  options?: string[];
  statements?: Statement[];
  answer: string;
  solution: string;
  citations: unknown[];
  check: unknown;
  [key: string]: unknown;
}

export interface Question {
  id: string;
  position: number;
  part: string;
  matrix_cell_id: string;
  content: QuestionContent;
  edited: boolean;
}

export interface CellRun {
  matrix_cell_id: string;
  sort_order: number;
  status: CellRunStatus;
  question_count: number;
  valid_count: number;
  rejected_count: number;
  error_message: string | null;
}

export interface Exam {
  id: string;
  matrix_id: string;
  owner_id: string;
  title: string;
  duration_minutes: number;
  status: ExamStatus;
  cells_done: number;
  cells_total: number;
  created_at: string;
  cell_runs: CellRun[];
  questions: Question[];
}

export interface BankEntry {
  id: string;
  exam_id: string;
  title: string;
  duration_minutes: number;
  subject: string;
  grade: number;
  matrix_name: string | null;
  is_visible: boolean;
  rag_status: IngestStatus;
  error_message: string | null;
  saved_by: { id: string; full_name: string };
  saved_at: string;
}

// Đề mẫu GV tải lên (T-050): bản nháp theo schema app.rag.chunking.exam của BE.
export type SubjectCode = "toan" | "ly" | "hoa";
export const SUBJECT_LABEL: Record<SubjectCode, string> = { toan: "Toán", ly: "Vật lí", hoa: "Hoá học" };
export type Part = "I" | "II" | "III";
// D-017: cùng bộ exam_kind với chỉ mục RAG và ma trận (T-055).
export const EXAM_KINDS: Record<string, string> = { tot_nghiep: "Tốt nghiệp / thi thử", dinh_ky_7991: "Định kỳ (giữa kì, cuối kì)" };

export interface DraftStatement {
  label: string;
  text: string;
  answer: boolean | null;
}

export interface DraftQuestion {
  part: Part;
  cau: number;
  topic?: string;
  level?: Level | "" | null;
  statement_levels?: (Level | "")[] | null;
  stem: string;
  figure?: string;
  options?: Record<string, string>;
  statements?: DraftStatement[];
  answer?: string;
  [key: string]: unknown;
}

export interface ExamDraft {
  exam: string;
  ma_de?: string;
  grade?: number;
  exam_kind?: string | null;
  questions: DraftQuestion[];
  [key: string]: unknown;
}

export interface DraftIssue {
  message: string;
  question: string | null;
}

export interface SampleExam {
  id: string;
  title: string;
  subject: SubjectCode;
  grade: number;
  original_filename: string;
  status: IngestStatus;
  error_message: string | null;
  created_at: string;
  draft: ExamDraft | null;
  issues: DraftIssue[];
}

export interface TopicOption {
  code: string;
  name: string;
  grade: number;
}
