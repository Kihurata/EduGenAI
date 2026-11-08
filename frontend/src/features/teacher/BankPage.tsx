import { useCallback, useEffect, useState } from "react";

import { api, download } from "@/api";
import { formatTime, useAction } from "@/common";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { BankEntry } from "@/types";

import { capCodes, codesLabel, exportRequest, FormError, parseCodes } from "./lib";

// NOTE: admin controls (show/hide for teachers, RAG status, remove from bank) moved to /admin/bank.
export default function BankPage() {
  const [items, setItems] = useState<BankEntry[] | null>(null);
  const [grade, setGrade] = useState("");
  const [q, setQ] = useState("");
  const [codesText, setCodesText] = useState("");
  const list = useAction();
  const action = useAction();

  const load = useCallback(() => {
    // API: GET /api/v1/bank[?grade=]
    void list.run(async () => setItems(await api<BankEntry[]>(grade ? `/bank?grade=${grade}` : "/bank")));
  }, [grade]);
  useEffect(load, [load]);

  const { codes, error: codesError } = parseCodes(codesText);
  const get = (id: string, variant: "student" | "teacher") => {
    const { path, fallback } = exportRequest(`/bank/${id}`, variant, codes);
    return action.run(() => download(path, fallback));
  };

  const shown = items?.filter((e) => e.title.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <section>
      <h1 className="mb-1 text-xl font-semibold">Ngân hàng đề</h1>
      <p className="mb-6 text-sm text-muted">Đề chính thức của trường do quản trị viên chọn.</p>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input className="max-w-xs" type="search" placeholder="Tìm theo tên đề" aria-label="Tìm theo tên đề" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="flex gap-1" role="group" aria-label="Lọc theo lớp">
          {["", "10", "11", "12"].map((g) => (
            <button
              key={g}
              type="button"
              aria-pressed={grade === g}
              onClick={() => setGrade(g)}
              className={cn(
                "h-8 cursor-pointer rounded-sm border px-3 text-sm",
                grade === g ? "border-accent bg-accent text-surface" : "border-line bg-surface",
              )}
            >
              {g ? `Lớp ${g}` : "Tất cả"}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <label htmlFor="bank-codes" className="text-muted">
            Mã đề khi tải
          </label>
          <Input
            id="bank-codes"
            className="w-44"
            value={codesText}
            onChange={(e) => setCodesText(capCodes(e.target.value, codesText).text)}
            placeholder="Trống = bản gốc; 101, 102…"
            aria-invalid={Boolean(codesError)}
            autoComplete="off"
          />
        </div>
      </div>
      {codesError && <p className="-mt-2 mb-3 text-right text-xs text-bad">{codesError}</p>}

      <FormError error={action.error} />
      {list.error && !items ? (
        <ErrorState message="Không tải được ngân hàng đề." onRetry={load} />
      ) : !shown ? (
        <p className="py-6 text-sm text-muted">Đang tải…</p>
      ) : shown.length === 0 ? (
        <EmptyState title={items?.length ? "Không có đề phù hợp" : "Ngân hàng trống"} hint={items?.length ? "Thử bỏ bớt bộ lọc." : "Quản trị viên chưa nạp đề nào."} />
      ) : (
        <ul className="divide-y divide-line border-y border-line">
          {shown.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{e.title}</p>
                <p className="text-muted">
                  Lớp {e.grade} · {e.duration_minutes} phút{e.matrix_name ? ` · ${e.matrix_name}` : ""} · {e.saved_by.full_name}, {formatTime(e.saved_at)}
                </p>
              </div>
              {/* API: GET /api/v1/bank/{id}/export?variant=student|teacher[&code=] (docx) · /export-variants?codes= (zip) */}
              <Button variant="outline" disabled={action.busy || Boolean(codesError)} onClick={() => get(e.id, "student")}>
                Bản học sinh{codes.length > 1 ? ` (${codesLabel(codes)})` : ""}
              </Button>
              <Button variant="outline" disabled={action.busy || Boolean(codesError)} onClick={() => get(e.id, "teacher")}>
                Bản giáo viên{codes.length > 1 ? ` (${codesLabel(codes)})` : ""}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
