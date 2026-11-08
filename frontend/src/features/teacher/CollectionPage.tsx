import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, download } from "@/api";
import { formatTime, useAction } from "@/common";
import { Chip } from "@/components/Chip";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, Td, Th } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { subjectLabel, useSubjects } from "@/subjects";
import type { Exam, ExamSource } from "@/types";

import { FormError, StatusChip } from "./lib";
import { REVIEW } from "./SourcePicker";

// Đề của GV, chia theo nguồn dữ liệu đã chọn khi sinh:
// - "Bộ sưu tập cá nhân": đề nguồn cá nhân, riêng của GV (admin không thấy). Quản lý: mở, tải, đổi tên, xoá.
// - "Đề gửi trường": đề nguồn trường, theo dõi quản trị viên đã xét chọn làm đề chính thức chưa.

const TABS: { key: ExamSource; label: string; hint: string }[] = [
  { key: "personal", label: "Bộ sưu tập cá nhân", hint: "Đề sinh từ bộ sưu tập cá nhân, chỉ bạn thấy. Duyệt xong đề được lưu ở đây." },
  { key: "school", label: "Đề gửi trường", hint: "Đề sinh từ dữ liệu của trường. Duyệt xong đề được gửi vào ngân hàng đề để quản trị viên xét chọn." },
];

type StatusFilter = "all" | "approved" | "draft";

export default function CollectionPage() {
  const subjects = useSubjects();
  const [tab, setTab] = useState<ExamSource>("personal");
  const [items, setItems] = useState<Exam[] | null>(null);
  const [q, setQ] = useState("");
  const [grade, setGrade] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [renaming, setRenaming] = useState<Exam | null>(null);
  const [deleting, setDeleting] = useState<Exam | null>(null);
  const list = useAction();
  const action = useAction();

  const load = useCallback(() => {
    setItems(null);
    // API: GET /api/v1/exams?source=personal|school (GV: chỉ đề của mình)
    void list.run(async () => setItems(await api<Exam[]>(`/exams?source=${tab}`)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);
  useEffect(load, [load]);

  const needle = q.trim().toLowerCase();
  const shown = items?.filter(
    (e) =>
      (!needle || e.title.toLowerCase().includes(needle)) &&
      (!grade || String(e.grade) === grade) &&
      (status === "all" || (status === "approved" ? e.status === "approved" : e.status !== "approved")),
  );
  const approvedCount = items?.filter((e) => e.status === "approved").length ?? 0;
  const current = TABS.find((t) => t.key === tab)!;

  const replace = (u: Exam) => setItems((p) => p?.map((x) => (x.id === u.id ? u : x)) ?? null);

  async function rename(exam: Exam, title: string) {
    // API: PATCH /api/v1/exams/{id} { title }
    const u = await action.run(() => api<Exam>(`/exams/${exam.id}`, { method: "PATCH", json: { title } }));
    if (u) replace(u);
  }

  async function remove(exam: Exam) {
    // API: DELETE /api/v1/exams/{id}
    const ok = await action.run(async () => {
      await api(`/exams/${exam.id}`, { method: "DELETE" });
      return true;
    });
    if (ok) setItems((p) => p?.filter((x) => x.id !== exam.id) ?? null);
  }

  return (
    <section>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Đề của tôi</h1>
        <Link to="/matrices" className="inline-flex h-9 items-center rounded-sm border border-accent bg-accent px-3 text-sm font-medium text-surface">
          Sinh đề mới
        </Link>
      </div>
      <p className="mb-5 text-sm text-muted">Quản lý đề bạn đã sinh, chia theo nguồn dữ liệu đã chọn lúc sinh đề.</p>

      <div className="mb-2 flex border-b border-line" role="tablist" aria-label="Nguồn đề">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "-mb-px cursor-pointer border-b-2 px-3 pb-2 text-sm",
              tab === t.key ? "border-accent font-medium text-ink" : "border-transparent text-muted",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="mb-4 text-xs text-muted">{current.hint}</p>

      {items && items.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Input
            className="w-64 max-w-full"
            type="search"
            placeholder="Tìm theo tên đề"
            aria-label="Tìm theo tên đề"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Segmented
            label="Lọc theo lớp"
            value={grade}
            onChange={setGrade}
            options={[["", "Mọi lớp"], ["10", "Lớp 10"], ["11", "Lớp 11"], ["12", "Lớp 12"]]}
          />
          <Segmented
            label="Lọc theo trạng thái"
            value={status}
            onChange={(v) => setStatus(v as StatusFilter)}
            options={[["all", "Tất cả"], ["approved", `Đã duyệt (${approvedCount})`], ["draft", `Đang soạn (${items.length - approvedCount})`]]}
          />
        </div>
      )}

      <FormError error={action.error} />

      {list.error && !items ? (
        <ErrorState message="Không tải được danh sách đề." onRetry={load} />
      ) : !shown ? (
        <p className="py-6 text-sm text-muted">Đang tải…</p>
      ) : shown.length === 0 ? (
        <EmptyState
          title={items?.length ? "Không có đề phù hợp" : tab === "personal" ? "Bộ sưu tập còn trống" : "Chưa có đề nào gửi trường"}
          hint={
            items?.length
              ? "Thử bỏ bớt bộ lọc."
              : tab === "personal"
                ? "Khi sinh đề, chọn nguồn “Bộ sưu tập cá nhân”. Đề duyệt xong sẽ được lưu ở đây."
                : "Khi sinh đề, chọn nguồn “Dữ liệu của trường”. Đề duyệt xong sẽ được gửi quản trị viên xét."
          }
        >
          {!items?.length && (
            <Link to="/matrices" className="text-accent underline">
              Sinh đề mới
            </Link>
          )}
        </EmptyState>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Đề</Th>
              <Th>Môn · Lớp</Th>
              <Th>Trạng thái</Th>
              {tab === "school" && <Th>Quản trị viên</Th>}
              <Th />
            </tr>
          </thead>
          <tbody>
            {shown.map((e) => {
              const approved = e.status === "approved";
              const official = e.review_status === "accepted";
              return (
                <tr key={e.id}>
                  <Td>
                    <Link to={`/exams/${e.id}`} className="font-medium text-accent underline">
                      {e.title}
                    </Link>
                    <div className="text-xs text-muted">
                      {e.questions.length} câu · {e.duration_minutes} phút · tạo {formatTime(e.created_at)}
                    </div>
                  </Td>
                  <Td>
                    {subjectLabel(subjects, e.subject) || "—"} · {e.grade ?? "—"}
                  </Td>
                  <Td>
                    <StatusChip status={e.status} />
                  </Td>
                  {tab === "school" && (
                    <Td>
                      {e.review_status ? (
                        <>
                          <Chip tone={REVIEW[e.review_status].tone}>{REVIEW[e.review_status].label}</Chip>
                          {e.review_status === "rejected" && e.review_note && (
                            <div className="mt-1 max-w-xs text-xs text-muted">Lý do: {e.review_note}</div>
                          )}
                        </>
                      ) : (
                        <span className="text-xs text-muted">Gửi khi bạn duyệt đề</span>
                      )}
                    </Td>
                  )}
                  <Td className="text-right">
                    <div className="flex flex-wrap justify-end gap-1">
                      {approved ? (
                        <>
                          <Button
                            variant="ghost"
                            disabled={action.busy}
                            onClick={() => action.run(() => download(`/exams/${e.id}/export?variant=student`, `${e.title} - HS.docx`))}
                          >
                            Tải bản HS
                          </Button>
                          <Button
                            variant="ghost"
                            disabled={action.busy}
                            onClick={() => action.run(() => download(`/exams/${e.id}/export?variant=teacher`, `${e.title} - GV.docx`))}
                          >
                            Tải bản GV
                          </Button>
                        </>
                      ) : (
                        <Link to={`/exams/${e.id}`} className="inline-flex h-9 items-center px-3 text-sm text-accent">
                          {e.status === "generating" ? "Xem tiến độ" : "Tiếp tục duyệt"}
                        </Link>
                      )}
                      {!official && (
                        <>
                          <Button variant="ghost" disabled={action.busy} onClick={() => setRenaming(e)}>
                            Đổi tên
                          </Button>
                          <Button
                            variant="ghost"
                            className="text-son"
                            disabled={action.busy || e.status === "generating"}
                            onClick={() => setDeleting(e)}
                          >
                            Xoá
                          </Button>
                        </>
                      )}
                    </div>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}

      <RenameDialog exam={renaming} onClose={() => setRenaming(null)} onSave={rename} />
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent title="Xoá đề?">
          <p className="text-sm text-muted">
            “{deleting?.title}” cùng toàn bộ câu hỏi và file đã xuất sẽ bị xoá vĩnh viễn. Ma trận gốc vẫn được giữ.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Hủy</Button>
            </DialogClose>
            <Button
              variant="danger"
              onClick={() => {
                if (deleting) void remove(deleting);
                setDeleting(null);
              }}
            >
              Xoá đề
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function Segmented({
  label,
  value,
  onChange,
  options,
}: Readonly<{ label: string; value: string; onChange: (v: string) => void; options: [string, string][] }>) {
  return (
    <div className="flex gap-1" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "h-8 cursor-pointer rounded-sm border px-3 text-sm",
            value === v ? "border-accent bg-accent text-surface" : "border-line bg-surface",
          )}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function RenameDialog({
  exam,
  onClose,
  onSave,
}: Readonly<{ exam: Exam | null; onClose: () => void; onSave: (exam: Exam, title: string) => void }>) {
  const [title, setTitle] = useState("");
  useEffect(() => {
    if (exam) setTitle(exam.title);
  }, [exam]);
  return (
    <Dialog open={!!exam} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Đổi tên đề">
        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            if (exam && title.trim()) onSave(exam, title.trim());
            onClose();
          }}
        >
          <label className="block text-sm">
            <span className="mb-1 block text-muted">Tên đề</span>
            <Input value={title} maxLength={255} onChange={(ev) => setTitle(ev.target.value)} autoFocus />
          </label>
          <div className="mt-5 flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Hủy
              </Button>
            </DialogClose>
            <Button type="submit" disabled={!title.trim() || title.trim() === exam?.title}>
              Lưu
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
