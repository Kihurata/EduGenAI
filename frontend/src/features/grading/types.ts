// Proposed contract types for Khối 2 (grading). No backend yet: see mock.ts.
export interface Student {
  code: string; // ma_hs
  name: string; // ho_ten
  dob: string; // ngay_sinh
}
export interface Class {
  id: string;
  name: string;
  students: Student[];
}
export interface ApprovedExam {
  id: string;
  title: string;
}
export interface AnswerSheet {
  id: string;
  examId: string;
  examTitle: string;
  classId: string;
  className: string;
  code: string; // mã đề
}
export type ScanStatus = "received" | "reading" | "blurry";
export type ReviewState = "pending" | "confirmed" | "skipped";
export type OcrFlag = "ok" | "doubtful" | "blank";
export type Letter = "A" | "B" | "C" | "D";
export interface OcrAnswer {
  q: number; // 1-based question number
  value: Letter | null;
  confidence: number; // 0..1
  flag: OcrFlag;
}
export interface ScanFile {
  id: string;
  fileName: string;
  status: ScanStatus;
  review: ReviewState;
  studentName: string;
  answers: OcrAnswer[];
}
export interface GradedResult {
  scanId: string;
  studentName: string;
  correct: number;
  total: number;
  score: number; // 0..10
}
export interface WeakTopic {
  topic: string;
  percentCorrect: number; // 0..100
}
export interface ResultsSummary {
  rows: GradedResult[];
  topics: WeakTopic[];
}
export interface ImportReport {
  created: number;
  errors: { row: number; message: string }[];
}
