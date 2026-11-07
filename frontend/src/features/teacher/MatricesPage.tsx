import { useCallback, useEffect, useState, type DragEvent, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "@/api";
import { formatTime, useAction, usePolling } from "@/common";
import { Stepper } from "@/components/Stepper";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Accepted, MatrixSummary } from "@/types";

import { FormError, StatusChip, teacherSteps } from "./lib";

const ACCEPT = ["image/png", "image/jpeg", "application/pdf", "application/json", ".json"];
const isJson = (f: File) => f.type === "application/json" || f.name.toLowerCase().endsWith(".json");
const MAX_BYTES = 20 * 1024 * 1024; // BE: settings.max_upload_mb

function fileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

function fileProblem(f: File): string {
  if (!isJson(f) && !ACCEPT.includes(f.type)) return "Định dạng chưa hỗ trợ. Chọn file PDF, PNG, JPG hoặc JSON.";
  if (f.size > MAX_BYTES) return "File lớn hơn 20 MB. Hãy nén ảnh hoặc tách bớt trang.";
  return "";
}

const STRUCTURE = [
  ["I · Nhiều lựa chọn", "0,25 đ/câu", 12, "3,0"],
  ["II · Đúng/Sai", "tối đa 1 đ/câu", 4, "4,0"],
  ["III · Trả lời ngắn", "0,5 đ/câu", 6, "3,0"],
] as const;

export default function MatricesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<MatrixSummary[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const list = useAction();
  const upload = useAction();

  const load = useCallback(() => {
    // API: GET /api/v1/matrices
    void list.run(async () => setItems(await api<MatrixSummary[]>("/matrices")));
  }, []);
  useEffect(load, [load]);
  usePolling(load, !!items?.some((m) => m.status === "uploaded" || m.status === "converting"));

  // Thumbnail for images; PDFs get a drawn page instead.
  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const problem = file ? fileProblem(file) : "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file || problem) return;
    const form = new FormData();
    form.append("file", file);
    // API: POST /api/v1/matrices (multipart)
    const accepted = await upload.run(() => api<Accepted>("/matrices", { method: "POST", form }));
    if (accepted) navigate(`/matrices/${accepted.id}`);
  }

  function pick(f: File | undefined | null) {
    upload.setError(null);
    setFile(f ?? null);
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    pick(e.dataTransfer.files[0]);
  }

  return (
    <section>
      <Stepper steps={teacherSteps()} current={0} />
      <p className="text-xs uppercase tracking-wider text-muted">Bước 1 trên 5</p>
      <h1 className="text-2xl font-semibold">Tải ma trận đề</h1>
      <p className="mt-1 max-w-2xl text-muted">
        Tải file ma trận đặc tả. Hệ thống đọc bảng và tách thành từng ô (chủ đề, dạng câu, mức độ, số câu) để bạn kiểm tra ở bước sau.
        Nếu đã có file JSON ma trận, tải thẳng lên: hệ thống đọc ngay, không cần AI.
      </p>

      <dl className="mt-5 mb-5 flex flex-wrap rounded-sm border border-line bg-surface text-sm">
        {[
          ["Môn", "Toán"],
          ["Lớp", "12"],
          ["Kỳ thi", "Tốt nghiệp THPT"],
        ].map(([k, v]) => (
          <div key={k} className="border-r border-line px-4 py-2">
            <dt className="text-xs uppercase tracking-wide text-muted">{k}</dt>
            <dd className="font-semibold">{v}</dd>
          </div>
        ))}
        <p className="min-w-56 flex-1 self-center px-4 py-2 text-muted">
          Phiên bản hiện tại hỗ trợ ma trận Toán 12 theo định dạng đề thi tốt nghiệp THPT từ năm 2025.
        </p>
      </dl>

      <div className="mb-10 grid items-start gap-8 border-b border-line pb-10 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <form onSubmit={submit} className="space-y-4">
          <input
            id="matrix-file"
            type="file"
            className="sr-only"
            accept={ACCEPT.join(",")}
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          {file ? (
            <div className="grid grid-cols-[6rem_minmax(0,1fr)] gap-5 rounded-sm border border-line bg-surface p-4 sm:grid-cols-[7rem_minmax(0,1fr)]">
              {preview ? (
                <img src={preview} alt="" className="aspect-[210/297] w-full border border-line object-cover object-top" />
              ) : (
                <div aria-hidden className="grid aspect-[210/297] w-full content-start gap-1 border border-line bg-white p-2">
                  <i className="mx-auto block h-0.5 w-2/3 bg-line" />
                  <i className="mx-auto mb-1 block h-0.5 w-1/2 bg-line" />
                  <div className="grid grid-cols-7 border-l border-t border-line">
                    {Array.from({ length: 42 }, (_, i) => (
                      <span key={i} className={cn("h-2 border-b border-r border-line", i < 7 && "bg-soft")} />
                    ))}
                  </div>
                </div>
              )}
              <div className="min-w-0 space-y-1">
                <p className="text-xs uppercase tracking-wide text-muted">File đã chọn</p>
                <p className="break-words font-semibold">{file.name}</p>
                <p className="text-sm text-muted">
                  {(file.name.split(".").pop() ?? "").toUpperCase()} · {fileSize(file.size)}
                </p>
                {problem ? (
                  <p className="text-sm text-bad">{problem}</p>
                ) : (
                  !upload.busy && <p className="text-sm font-medium text-ok">✓ Đúng định dạng, sẵn sàng tải lên</p>
                )}
                {upload.busy ? (
                  <p className="flex items-center gap-2 pt-2 text-sm text-accent">
                    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-r-transparent" />
                    {isJson(file) ? "Đang tải lên và đọc file JSON…" : "Đang tải lên và đọc bảng ma trận…"}
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2 pt-2">
                    <label htmlFor="matrix-file" className="inline-flex h-8 cursor-pointer items-center rounded-sm border border-line bg-surface px-3 text-sm font-medium hover:bg-soft">
                      Đổi file
                    </label>
                    <Button type="button" variant="ghost" className="h-8 hover:bg-soft" onClick={() => pick(null)}>
                      Bỏ chọn
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <label
              htmlFor="matrix-file"
              onDragOver={(e) => {
                e.preventDefault();
                setOver(true);
              }}
              onDragLeave={() => setOver(false)}
              onDrop={drop}
              className={cn(
                "flex cursor-pointer flex-col items-center gap-2 rounded-sm border-[1.5px] border-dashed px-6 py-12 text-center",
                over ? "border-accent bg-soft" : "border-line bg-surface hover:border-accent",
              )}
            >
              <span aria-hidden className="mb-1 grid h-12 w-12 place-items-center rounded-full bg-accent/10 text-accent">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 16V4" />
                  <path d="m6 10 6-6 6 6" />
                  <path d="M4 20h16" />
                </svg>
              </span>
              <span className="text-base font-semibold">Kéo thả file ma trận vào đây</span>
              <span className="text-sm text-muted">hoặc bấm để chọn file từ máy</span>
              <span className="mt-1 flex flex-wrap justify-center gap-1.5 text-xs text-muted">
                {["PDF", "PNG", "JPG", "JSON", "tối đa 20 MB"].map((t) => (
                  <span key={t} className="rounded-full border border-line px-2 py-0.5">
                    {t}
                  </span>
                ))}
              </span>
            </label>
          )}

          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={!file || !!problem || upload.busy}>
              {upload.busy ? "Đang xử lý…" : "Tải lên và kiểm tra"}
            </Button>
            <span className="text-sm text-muted">
              {file && isJson(file) ? "File JSON được đọc ngay, không gọi AI." : "Thường mất 20–40 giây với file 2 trang."}
            </span>
          </div>
          <FormError error={upload.error} />
        </form>

        <aside className="space-y-6 text-sm lg:border-l lg:border-line lg:pl-7" aria-label="Yêu cầu file ma trận">
          <div className="space-y-3">
            <h2 className="text-base font-semibold">File ma trận cần có</h2>
            <ul className="space-y-2">
              {[
                "Cột chủ đề và nội dung (đơn vị kiến thức)",
                "Số câu theo từng mức độ Biết, Hiểu, Vận dụng",
                "Tách 3 phần theo dạng câu hỏi",
                "Ảnh chụp rõ nét, đủ các cột, không bị cắt mép",
              ].map((t) => (
                <li key={t} className="grid grid-cols-[1.1rem_1fr] gap-2">
                  <span className="font-semibold text-ok">✓</span>
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Cấu trúc chuẩn để đối chiếu</h3>
            <table className="w-full border-collapse">
              <thead>
                <tr className="text-xs text-muted">
                  <th className="border-b border-line py-1.5 text-left font-medium">Phần</th>
                  <th className="border-b border-line py-1.5 text-right font-medium">Số câu</th>
                  <th className="border-b border-line py-1.5 text-right font-medium">Điểm</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {STRUCTURE.map(([part, rule, n, pts]) => (
                  <tr key={part}>
                    <td className="border-b border-line py-1.5">
                      {part} <span className="text-muted">({rule})</span>
                    </td>
                    <td className="border-b border-line py-1.5 text-right">{n}</td>
                    <td className="border-b border-line py-1.5 text-right">{pts}</td>
                  </tr>
                ))}
                <tr className="font-semibold">
                  <td className="py-1.5">Tổng</td>
                  <td className="py-1.5 text-right">22</td>
                  <td className="py-1.5 text-right">10</td>
                </tr>
              </tbody>
            </table>
          </div>
        </aside>
      </div>

      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold">Ma trận gần đây</h2>
        {items && items.length > 0 && <span className="text-sm text-muted">{items.length} ma trận</span>}
      </div>
      {list.error && !items ? (
        <ErrorState message="Không tải được danh sách ma trận." onRetry={load} />
      ) : !items ? (
        <p className="py-6 text-sm text-muted">Đang tải…</p>
      ) : items.length === 0 ? (
        <EmptyState title="Chưa có ma trận nào" hint="Tải file ma trận ở trên để bắt đầu." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="border-b border-line px-2 py-2 font-medium">Tên ma trận</th>
                <th className="border-b border-line px-2 py-2 font-medium">Lớp</th>
                <th className="border-b border-line px-2 py-2 font-medium">Trạng thái</th>
                <th className="border-b border-line px-2 py-2 font-medium">Tải lên</th>
                <th className="border-b border-line px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr key={m.id} className="hover:bg-soft/50">
                  <td className="border-b border-line px-2 py-3">
                    <Link to={`/matrices/${m.id}`} className="font-medium text-accent">
                      {m.name ?? m.source_filename}
                    </Link>
                    {m.name && <div className="break-all text-xs text-muted">{m.source_filename}</div>}
                  </td>
                  <td className="border-b border-line px-2 py-3">{m.grade ?? "–"}</td>
                  <td className="border-b border-line px-2 py-3">
                    <StatusChip status={m.status} />
                  </td>
                  <td className="whitespace-nowrap border-b border-line px-2 py-3 tabular-nums text-muted">{formatTime(m.created_at)}</td>
                  <td className="border-b border-line px-2 py-3 text-right">
                    <Link to={`/matrices/${m.id}`} className="whitespace-nowrap text-accent">
                      Mở →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
