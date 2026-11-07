// Tóm tắt: danh sách môn từ API GET /subjects (D-020, T-064): tên, tên ngắn và cấu trúc đề từng môn. Các trang đọc từ đây
// thay vì ghi cứng Toán và 12/4/6; tải một lần cho cả phiên.
import { useEffect, useState } from "react";

import { api } from "./api";
import type { QuestionType } from "./types";

export interface Subject {
  code: string;
  name: string; // tên chính thức, như dòng "Môn:" của ma trận
  label: string; // tên ngắn để hiển thị
  duration_minutes: number;
  question_counts: Record<QuestionType, number>;
  points: Record<QuestionType, number>;
}

let cache: Promise<Subject[]> | null = null;

export function useSubjects(): Subject[] | null {
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  useEffect(() => {
    cache ??= api<Subject[]>("/subjects").catch((e: unknown) => {
      cache = null; // thử lại ở lần mở trang sau
      throw e;
    });
    let alive = true;
    cache.then((s) => alive && setSubjects(s)).catch(() => alive && setSubjects([]));
    return () => {
      alive = false;
    };
  }, []);
  return subjects;
}

/** Tên ngắn của môn; chưa tải xong hoặc mã lạ thì trả lại chính mã. */
export function subjectLabel(subjects: Subject[] | null, code: string | null | undefined): string {
  return subjects?.find((s) => s.code === code)?.label ?? code ?? "";
}
