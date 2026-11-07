// Mock store for Khối 2 (grading). State lives at module level so actions persist across navigation.
import { delay } from "@/lib/mock";

import type { AnswerSheet, ApprovedExam, Class, ImportReport, Letter, OcrAnswer, ResultsSummary, ScanFile } from "./types";

const LETTERS: Letter[] = ["A", "B", "C", "D"];
export const QUESTION_COUNT = 12;
const KEY: Letter[] = ["A", "C", "B", "D", "A", "B", "C", "D", "B", "A", "D", "C"];
const TOPICS = ["Hàm số", "Mũ – Logarit", "Nguyên hàm – Tích phân", "Hình học không gian"];
const topicOf = (q: number) => TOPICS[Math.floor((q - 1) / 3)];

const exams: ApprovedExam[] = [
  { id: "e1", title: "Toán 12 – Giữa kỳ I (đề 01)" },
  { id: "e2", title: "Toán 12 – Cuối kỳ I (đề 02)" },
  { id: "e3", title: "Toán 12 – Thi thử THPT (đề 03)" },
];
const classes: Class[] = [
  {
    id: "c1",
    name: "12A1",
    students: [
      { code: "HS001", name: "Nguyễn Văn An", dob: "2008-03-14" },
      { code: "HS002", name: "Trần Thị Bình", dob: "2008-07-02" },
      { code: "HS003", name: "Lê Minh Châu", dob: "2008-11-21" },
    ],
  },
  { id: "c2", name: "12A2", students: [{ code: "HS101", name: "Phạm Quốc Dũng", dob: "2008-01-30" }] },
];
let sheets: AnswerSheet[] = [];
let scans: ScanFile[] = [];
let seq = 0;
const uid = (p: string) => `${p}${++seq}`;

// shortcut: in-memory only, a page reload resets everything; replaced by API calls when the BE exists.

export async function getClasses(): Promise<Class[]> {
  // TODO(BE): GET /api/v1/classes
  //   req : none
  //   res : [{ id, name, students: [{ code, name, dob }] }]  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  return delay(structuredClone(classes));
}
export async function getClass(id: string): Promise<Class | null> {
  // TODO(BE): GET /api/v1/classes/{class_id}
  //   req : none
  //   res : { id, name, students: [{ code, name, dob }] } or 404  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  return delay(structuredClone(classes.find((c) => c.id === id) ?? null));
}
export async function addClass(name: string): Promise<Class> {
  // TODO(BE): POST /api/v1/classes
  //   req : { name: string }
  //   res : { id, name, students: [] }  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  const c: Class = { id: uid("c"), name, students: [] };
  classes.push(c);
  return delay(structuredClone(c));
}

/** Parses CSV text (header ma_hs,ho_ten,ngay_sinh optional), adds valid rows, reports row errors. */
export async function importStudents(classId: string, csv: string): Promise<ImportReport> {
  // TODO(BE): POST /api/v1/classes/{class_id}/students/import (multipart CSV)
  //   req : file=ma_hs,ho_ten,ngay_sinh
  //   res : { created: number, errors: [{row: number, message: string}] }  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  const cls = classes.find((c) => c.id === classId);
  if (!cls) return delay({ created: 0, errors: [{ row: 0, message: "Không tìm thấy lớp." }] });
  const report: ImportReport = { created: 0, errors: [] };
  const seen = new Set(cls.students.map((s) => s.code));
  csv.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    if (!line || (i === 0 && /ma_hs/i.test(line))) return;
    const [code = "", name = "", dob = ""] = line.split(",").map((x) => x.trim());
    const row = i + 1;
    if (!code || !name) report.errors.push({ row, message: "Thiếu mã học sinh hoặc họ tên." });
    else if (seen.has(code)) report.errors.push({ row, message: `Trùng mã học sinh ${code}.` });
    else {
      seen.add(code);
      cls.students.push({ code, name, dob });
      report.created++;
    }
  });
  return delay(report);
}

export async function getApprovedExams(): Promise<ApprovedExam[]> {
  // TODO(BE): GET /api/v1/exams?status=approved
  //   req : query status=approved
  //   res : [{ id, title }]  (exams endpoint exists; confirm the status filter)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  return delay(exams);
}
export async function getSheets(): Promise<AnswerSheet[]> {
  // TODO(BE): GET /api/v1/answer-sheets
  //   req : none
  //   res : [{ id, examId, examTitle, classId, className, code }]  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  return delay([...sheets]);
}
export async function createSheets(examId: string, classId: string, versions: number): Promise<AnswerSheet[]> {
  // TODO(BE): POST /api/v1/answer-sheets
  //   req : { exam_id: string, class_id: string, versions: number }
  //   res : [{ id, examId, examTitle, classId, className, code }]; PDF via GET /api/v1/answer-sheets/{id}/pdf  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  const exam = exams.find((e) => e.id === examId);
  const cls = classes.find((c) => c.id === classId);
  if (!exam || !cls) throw new Error("invalid exam or class");
  sheets = Array.from({ length: versions }, (_, i) => ({
    id: uid("s"), examId, examTitle: exam.title, classId, className: cls.name, code: String(101 + i),
  }));
  return delay([...sheets]);
}

const pickStudent = (i: number) => {
  const all = classes.flatMap((c) => c.students);
  return all.length ? all[i % all.length].name : `Học sinh ${i + 1}`;
};
function fakeAnswers(): OcrAnswer[] {
  return Array.from({ length: QUESTION_COUNT }, (_, i) => {
    const r = Math.random();
    const q = i + 1;
    if (r < 0.08) return { q, value: null, confidence: 0, flag: "blank" };
    const value = Math.random() < 0.7 ? KEY[i] : LETTERS[Math.floor(Math.random() * 4)];
    if (r < 0.25) return { q, value, confidence: 0.5 + Math.random() * 0.25, flag: "doubtful" };
    return { q, value, confidence: 0.9 + Math.random() * 0.09, flag: "ok" };
  });
}

export async function getScans(): Promise<ScanFile[]> {
  // TODO(BE): GET /api/v1/scans
  //   req : none
  //   res : [{ id, fileName, status: received|reading|blurry, review: pending|confirmed|skipped, studentName }]  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  return delay(structuredClone(scans), 150);
}
export async function getScan(id: string): Promise<ScanFile | null> {
  // TODO(BE): GET /api/v1/scans/{scan_id}
  //   req : none
  //   res : { id, fileName, status, review, studentName, answers: [{ q, value, confidence, flag }] } or 404  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  return delay(structuredClone(scans.find((s) => s.id === id) ?? null));
}
export async function uploadScans(fileNames: string[]): Promise<void> {
  // TODO(BE): POST /api/v1/scans (multipart images; OCR runs async, poll GET /api/v1/scans)
  //   req : files[]=image/*|pdf
  //   res : [{ id, fileName, status: "reading" }]  (proposed contract)
  //   owner: Backend (Huy/Phu) + OCR (Dong) · feature: Khối 2 · now: mock in features/grading/mock.ts (timers)
  const created = fileNames.map<ScanFile>((fileName, i) => ({
    id: uid("x"), fileName, status: "reading", review: "pending", studentName: pickStudent(scans.length + i), answers: fakeAnswers(),
  }));
  const base = scans.length;
  scans = [...scans, ...created];
  created.forEach((s, i) => {
    setTimeout(() => {
      const t = scans.find((x) => x.id === s.id);
      if (t) t.status = (base + i) % 4 === 3 ? "blurry" : "received";
    }, 1500 + i * 700);
  });
  return delay(undefined, 150);
}
export async function fixAnswer(scanId: string, q: number, value: Letter): Promise<void> {
  // TODO(BE): PATCH /api/v1/scans/{scan_id}/answers/{q}
  //   req : { value: "A"|"B"|"C"|"D" }
  //   res : { q, value, confidence: 1, flag: "ok" }  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  const a = scans.find((s) => s.id === scanId)?.answers.find((x) => x.q === q);
  if (a) Object.assign(a, { value, confidence: 1, flag: "ok" });
  return delay(undefined, 100);
}
export async function setReview(scanId: string, review: "confirmed" | "skipped"): Promise<void> {
  // TODO(BE): POST /api/v1/scans/{scan_id}/confirm  |  POST /api/v1/scans/{scan_id}/skip
  //   req : none
  //   res : { id, review }; confirm triggers grading  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
  const s = scans.find((x) => x.id === scanId);
  if (s) s.review = review;
  return delay(undefined, 150);
}
/** Next scan waiting for review (read OK, not yet reviewed), optionally excluding one. */
export const nextReviewable = (list: ScanFile[], exceptId?: string) =>
  list.find((s) => s.status === "received" && s.review === "pending" && s.id !== exceptId);

export async function getResults(): Promise<ResultsSummary> {
  // TODO(BE): GET /api/v1/results?class_id=
  //   req : query class_id (optional)
  //   res : { rows: [{ scanId, studentName, correct, total, score }], topics: [{ topic, percentCorrect }] }  (proposed contract)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts (graded from a fixed key, Phần I only)
  const done = scans.filter((s) => s.review === "confirmed");
  const rows = done.map((s) => {
    const correct = s.answers.filter((a) => a.value === KEY[a.q - 1]).length;
    return { scanId: s.id, studentName: s.studentName, correct, total: QUESTION_COUNT, score: Math.round((correct / QUESTION_COUNT) * 100) / 10 };
  });
  const topics = TOPICS.map((topic) => {
    const qs = done.flatMap((s) => s.answers.filter((a) => topicOf(a.q) === topic));
    const ok = qs.filter((a) => a.value === KEY[a.q - 1]).length;
    return { topic, percentCorrect: qs.length ? Math.round((ok / qs.length) * 100) : 0 };
  });
  return delay({ rows, topics });
}
export function exportCsv(rows: ResultsSummary["rows"]) {
  // TODO(BE): GET /api/v1/results/export.csv?class_id=
  //   req : query class_id (optional)
  //   res : text/csv (hoc_sinh,so_cau_dung,diem)  (proposed contract; client-side CSV for now)
  //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: client-side from mock
  const csv = ["hoc_sinh,so_cau_dung,diem", ...rows.map((r) => `"${r.studentName}",${r.correct},${r.score}`)].join("\n");
  const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  Object.assign(document.createElement("a"), { href: url, download: "bang-diem.csv" }).click();
  URL.revokeObjectURL(url);
}
