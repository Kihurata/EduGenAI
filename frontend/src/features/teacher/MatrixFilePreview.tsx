// Tóm tắt: xem trước file ma trận giáo viên vừa chọn ở bước 1, trước khi tải lên. Ảnh hiện đúng ảnh, PDF hiện trang
// PDF, JSON vẽ lại bảng ma trận (dòng nội dung × Phần I/II/III × Biết/Hiểu/Vận dụng) từ chính file. Bấm ô xem nhỏ để mở to.
import { useEffect, useState } from "react";

import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const PARTS = [
  { key: "multiple_choice", label: "Phần I · Nhiều lựa chọn" },
  { key: "true_false_statements", label: "Phần II · Đúng/Sai (ý)" },
  { key: "short_answer", label: "Phần III · Trả lời ngắn" },
] as const;
const LEVELS = [
  { keys: ["biet"], label: "B" },
  { keys: ["hieu"], label: "H" },
  { keys: ["van_dung", "vandung"], label: "VD" },
] as const;

interface JsonMatrix {
  name: string;
  rows: { unit: string; counts: number[] }[]; // 9 số: Phần I B/H/VD, Phần II B/H/VD, Phần III B/H/VD
}

/** Đọc JSON ma trận (định dạng `rows[].multiple_choice.biet`…) thành bảng để xem; sai định dạng → null. */
function readJsonMatrix(text: string): JsonMatrix | null {
  try {
    const data = JSON.parse(text) as { name?: unknown; rows?: unknown };
    if (!Array.isArray(data.rows)) return null;
    const rows = data.rows.flatMap((r: Record<string, unknown>) => {
      const unit = typeof r?.unit_name === "string" ? r.unit_name.trim() : "";
      if (!unit) return [];
      const counts = PARTS.flatMap(({ key }) => {
        const part = (r[key] ?? {}) as Record<string, unknown>;
        return LEVELS.map(({ keys }) => Number(keys.map((k) => part[k]).find((v) => v != null) ?? 0) || 0);
      });
      return [{ unit, counts }];
    });
    return rows.length ? { name: typeof data.name === "string" ? data.name : "", rows } : null;
  } catch {
    return null;
  }
}

function MatrixTable({ m, tiny = false }: Readonly<{ m: JsonMatrix; tiny?: boolean }>) {
  const cell = cn("border border-line", tiny ? "px-px leading-none" : "px-2 py-1");
  const totals = m.rows[0].counts.map((_, i) => m.rows.reduce((s, r) => s + r.counts[i], 0));
  return (
    <table className={cn("w-full border-collapse bg-white text-center tabular-nums", tiny ? "text-[4px]" : "text-sm")}>
      <thead className="bg-soft">
        <tr>
          <th rowSpan={2} className={cn(cell, "text-left")}>
            Nội dung
          </th>
          {PARTS.map((p) => (
            <th key={p.key} colSpan={3} className={cell}>
              {tiny ? "" : p.label}
            </th>
          ))}
        </tr>
        <tr>
          {PARTS.flatMap((p) =>
            LEVELS.map((l) => (
              <th key={p.key + l.label} className={cn(cell, "font-medium")}>
                {tiny ? "" : l.label}
              </th>
            )),
          )}
        </tr>
      </thead>
      <tbody>
        {m.rows.map((r, ri) => (
          <tr key={`${ri}-${r.unit}`}>
            <td className={cn(cell, "text-left")}>{tiny ? <i className="block h-px w-full bg-line" /> : r.unit}</td>
            {r.counts.map((n, i) => (
              <td key={i} className={cn(cell, !n && "text-line")}>
                {n || "·"}
              </td>
            ))}
          </tr>
        ))}
        {!tiny && (
          <tr className="bg-soft font-semibold">
            <td className={cn(cell, "text-left")}>Tổng</td>
            {totals.map((n, i) => (
              <td key={i} className={cell}>
                {n}
              </td>
            ))}
          </tr>
        )}
      </tbody>
    </table>
  );
}

const isJsonFile = (f: File) => f.type === "application/json" || f.name.toLowerCase().endsWith(".json");

/** Ô xem nhỏ (A4 dọc) của file đã chọn; bấm để mở bản to. */
export function MatrixFilePreview({ file }: Readonly<{ file: File }>) {
  const [url, setUrl] = useState<string | null>(null);
  const [json, setJson] = useState<JsonMatrix | null>(null);
  const kind = file.type.startsWith("image/") ? "image" : file.type === "application/pdf" ? "pdf" : isJsonFile(file) ? "json" : "other";

  useEffect(() => {
    if (kind !== "image" && kind !== "pdf") return;
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => {
      URL.revokeObjectURL(u);
      setUrl(null);
    };
  }, [file, kind]);

  useEffect(() => {
    setJson(null);
    if (kind !== "json") return;
    let alive = true;
    void file.text().then((t) => alive && setJson(readJsonMatrix(t)));
    return () => {
      alive = false;
    };
  }, [file, kind]);

  const box = "aspect-[210/297] w-full overflow-hidden border border-line bg-white";
  let thumb;
  if (kind === "image" && url) thumb = <img src={url} alt="" className={cn(box, "object-cover object-top")} />;
  else if (kind === "json" && json)
    thumb = (
      <div className={cn(box, "p-1.5")}>
        <p className="mb-1 truncate text-center text-[5px] font-semibold uppercase">{json.name || "Ma trận"}</p>
        <MatrixTable m={json} tiny />
      </div>
    );
  else
    thumb = (
      <div aria-hidden className={cn(box, "grid content-start gap-1 p-2")}>
        <i className="mx-auto block h-0.5 w-2/3 bg-line" />
        <i className="mx-auto mb-1 block h-0.5 w-1/2 bg-line" />
        <div className="grid grid-cols-7 border-l border-t border-line">
          {Array.from({ length: 42 }, (_, i) => (
            <span key={i} className={cn("h-2 border-b border-r border-line", i < 7 && "bg-soft")} />
          ))}
        </div>
      </div>
    );

  const canOpen = (kind === "image" || kind === "pdf") ? !!url : kind === "json" && !!json;
  if (!canOpen) return thumb;
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button type="button" className="group relative block w-full cursor-zoom-in text-left" aria-label={`Xem trước ${file.name}`}>
          {thumb}
          {/* luôn hiện (máy cảm ứng không có hover) */}
          <span aria-hidden className="absolute right-1 bottom-1 grid h-6 w-6 place-items-center rounded-sm bg-ink/70 text-surface group-hover:bg-accent group-focus-visible:bg-accent">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5M11 8v6M8 11h6" />
            </svg>
          </span>
        </button>
      </DialogTrigger>
      <DialogContent title={json?.name || file.name} className="w-[min(64rem,94vw)]">
        <div className="max-h-[75vh] overflow-auto">
          {kind === "image" && url && <img src={url} alt={file.name} className="mx-auto max-w-full" />}
          {kind === "pdf" && url && <iframe src={url} title={file.name} className="h-[70vh] w-full border border-line" />}
          {kind === "json" && json && <MatrixTable m={json} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export const JSON_FORMAT_ERROR =
  "File JSON không đúng định dạng ma trận: cần danh sách “rows”, mỗi dòng có “unit_name” và số câu theo mức độ.";

export interface FileCheck {
  summary: string | null; // JSON hợp lệ: số dòng nội dung, số câu từng phần
  error: string | null; // JSON đọc không được: báo ngay ở bước 1, không cho tải lên
  previewable: boolean; // ô xem nhỏ bấm được để xem to
}

/** Đọc trước file đã chọn: tóm tắt / lỗi định dạng của JSON, và file có xem trước được không. */
export function useFileCheck(file: File | null): FileCheck {
  const [json, setJson] = useState<{ file: File; m: JsonMatrix | null } | null>(null);
  useEffect(() => {
    if (!file || !isJsonFile(file)) return;
    let alive = true;
    void file.text().then((t) => alive && setJson({ file, m: readJsonMatrix(t) }));
    return () => {
      alive = false;
    };
  }, [file]);
  if (!file) return { summary: null, error: null, previewable: false };
  if (!isJsonFile(file)) {
    const media = file.type.startsWith("image/") || file.type === "application/pdf";
    return { summary: null, error: null, previewable: media };
  }
  if (json?.file !== file) return { summary: null, error: null, previewable: false }; // đang đọc
  const m = json.m;
  if (!m) return { summary: null, error: JSON_FORMAT_ERROR, previewable: false };
  const part = (p: number) => m.rows.reduce((s, r) => s + r.counts[p * 3] + r.counts[p * 3 + 1] + r.counts[p * 3 + 2], 0);
  return {
    summary: `${m.rows.length} dòng nội dung · Phần I ${part(0)} câu · Phần II ${part(1)} ý · Phần III ${part(2)} câu`,
    error: null,
    previewable: true,
  };
}
