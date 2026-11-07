import { useEffect, useState } from "react";

import { api, ApiError } from "@/api";
import { Chip, type ChipTone } from "@/components/Chip";
import type { Step } from "@/components/Stepper";
import { TYPE_LABEL, type Cell, type Matrix } from "@/types";

const STATUS: Record<string, [string, ChipTone]> = {
  uploaded: ["Đã tải lên", "muted"],
  converting: ["Đang đọc ảnh", "muted"],
  parsed: ["Đã đọc", "accent"],
  invalid: ["Có lỗi", "warn"],
  confirmed: ["Đã xác nhận", "ok"],
  failed: ["Lỗi", "bad"],
  generating: ["Đang sinh", "muted"],
  generated: ["Đã sinh", "ok"],
  incomplete: ["Thiếu câu", "warn"],
  approved: ["Đã duyệt", "ok"],
  complete: ["Đủ câu", "ok"],
  short: ["Thiếu câu", "warn"],
  error: ["Lỗi", "bad"],
  pending: ["Chờ gửi", "muted"],
  sent: ["Đã gửi RAG", "accent"],
  ingested: ["RAG đã học", "ok"],
};

export function StatusChip({ status }: Readonly<{ status: string }>) {
  const [label, tone] = STATUS[status] ?? [status, "muted" as ChipTone];
  return <Chip tone={tone}>{label}</Chip>;
}

export function errText(error: unknown): string {
  if (error instanceof ApiError) return error.messages.join("; ") || error.message;
  if (error instanceof Error) return error.message;
  return error ? String(error) : "";
}

export function FormError({ error }: Readonly<{ error: unknown }>) {
  return error ? (
    <p role="alert" className="text-sm text-bad">
      {errText(error)}
    </p>
  ) : null;
}

/** Teacher stepper steps; later steps link only once the matrix / exam id is known. */
export function teacherSteps(o: { matrix?: string; exam?: string } = {}): Step[] {
  return [
    { label: "Ma trận", to: "/matrices" },
    { label: "Kiểm tra", to: o.matrix ? `/matrices/${o.matrix}` : undefined },
    { label: "Sinh đề", to: "/exams" },
    { label: "Duyệt", to: o.exam ? `/exams/${o.exam}` : undefined },
    { label: "Xuất", to: o.exam ? `/exams/${o.exam}/export` : undefined },
  ];
}

export function cellLabel(c: Cell | undefined, sortOrder: number): string {
  if (!c) return `Ô ${sortOrder}`;
  const topic = c.content_unit ? `${c.topic} – ${c.content_unit}` : c.topic;
  return `Ô ${sortOrder}: ${topic} (${TYPE_LABEL[c.type]}, ${c.level})`;
}

// API: GET /api/v1/matrices/{id} — cells of the matrix an exam came from (for readable cell labels).
export function useMatrixCells(matrixId: string | undefined): Record<string, Cell> {
  const [cells, setCells] = useState<Record<string, Cell>>({});
  useEffect(() => {
    if (!matrixId) return;
    api<Matrix>(`/matrices/${matrixId}`)
      .then((m) => setCells(Object.fromEntries(m.cells.map((c) => [c.id, c]))))
      .catch(() => setCells({}));
  }, [matrixId]);
  return cells;
}

export const taClass = "w-full rounded-sm border border-line bg-surface px-3 py-2 text-sm text-ink";

// Official THPT Toán structure (QĐ 764/2024): 12 + 4 + 6 questions, 10 points.
export const OFFICIAL_COUNTS: Record<string, number> = { multiple_choice: 12, true_false: 4, short_answer: 6 };
export const POINTS: Record<string, number> = { multiple_choice: 0.25, true_false: 1, short_answer: 0.5 };

export const PARTS = [
  { part: "I", type: "multiple_choice" },
  { part: "II", type: "true_false" },
  { part: "III", type: "short_answer" },
] as const;

// Official part instructions, shared by the review document and the A4 export preview.
export const PART_HEAD: Record<string, [string, string]> = {
  multiple_choice: ["PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn.", "Mỗi câu hỏi thí sinh chỉ chọn một phương án."],
  true_false: ["PHẦN II. Câu trắc nghiệm đúng sai.", "Trong mỗi ý a), b), c), d) ở mỗi câu, thí sinh chọn đúng hoặc sai."],
  short_answer: ["PHẦN III. Câu trắc nghiệm trả lời ngắn.", "Thí sinh ghi đáp số vào phiếu trả lời."],
};

export const LETTERS = "ABCD";

const MATH_SPLIT = /(\$\$[\s\S]+?\$\$|\$[^$]+?\$)/g;

/** Splits a solution into steps: by line breaks, otherwise by sentences (never inside $...$). */
export function solutionSteps(text: string): string[] {
  const byLine = text
    .split(/\n+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (byLine.length > 1) return byLine;
  const steps: string[] = [];
  let buf = "";
  text.split(MATH_SPLIT).forEach((part, i) => {
    if (i % 2 === 1) {
      buf += part;
      return;
    }
    part.split(/(?<=\.)\s+/).forEach((seg, k) => {
      if (k > 0) {
        if (buf.trim()) steps.push(buf.trim());
        buf = "";
      }
      buf += seg;
    });
  });
  if (buf.trim()) steps.push(buf.trim());
  return steps;
}

/** Default exam title from the matrix name: "Ma trận đề kiểm tra…" becomes "Đề kiểm tra…". */
export function examTitleFromMatrix(name: string | null | undefined): string {
  if (!name) return "";
  const trimmed = name.trim();
  const rest = trimmed.replace(/^ma\s+trận\s+(?:đề\s+)?/iu, "").trim();
  if (rest === trimmed || !rest) return trimmed;
  return (trimmed === trimmed.toUpperCase() ? "ĐỀ " : "Đề ") + rest;
}

/**
 * Column count for multiple-choice options, from the longest option's rough rendered length
 * (a LaTeX command counts as one glyph). `wide` is the A4 page; otherwise the narrower review column.
 */
export function optionColumns(options: string[], wide = false): 1 | 2 | 4 {
  const glyphs = (o: string) => o.replace(/\\[a-zA-Z]+/g, "x").replace(/[${}^_\s]/g, "").length;
  const len = Math.max(...options.map(glyphs));
  if (len <= (wide ? 12 : 5)) return 4;
  return len <= (wide ? 30 : 22) ? 2 : 1;
}

/** Some generated options carry LaTeX without $...$ (e.g. "(\infty; 2)"); wrap those so they render as math. */
export function mathOption(o: string): string {
  return !o.includes("$") && /\\[a-zA-Z]+/.test(o) ? `$${o}$` : o;
}

// Serif face of printed Vietnamese exams (the .docx export uses Times New Roman).
export const PAPER_FONT = "font-['Times_New_Roman',Tinos,Times,serif]";
