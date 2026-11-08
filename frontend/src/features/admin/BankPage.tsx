import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api";
import { formatTime } from "@/common";
import { Chip, type ChipTone } from "@/components/Chip";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, Td, Th } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { BankEntry, Exam, ExamStatus, User } from "@/types";
import { ConfirmDialog, errText, Failed, Loading, useLoad } from "./shared";

// Ngân hàng đề (admin): xem đề GV sinh từ dữ liệu của trường, chọn đề nào là đề CHÍNH THỨC cho kỳ thi của trường.
// GV duyệt xong đề nguồn trường thì đề tự vào hàng chờ (review_status = pending). "Chính thức" = có trong ngân hàng
// (POST /bank → accepted); "Không chọn" = POST /bank/reject kèm lý do. Đề trong bộ sưu tập cá nhân của GV không hiện ở đây.

const EXAM_STATUS: Record<ExamStatus, { label: string; tone: ChipTone }> = {
  generating: { label: "Đang sinh", tone: "accent" },
  generated: { label: "Chưa duyệt", tone: "muted" },
  incomplete: { label: "Thiếu câu", tone: "warn" },
  failed: { label: "Lỗi sinh đề", tone: "bad" },
  approved: { label: "GV đã duyệt", tone: "ok" },
};
const RAG = { pending: "Chờ nạp", needs_review: "Chờ duyệt", sent: "Đang nạp", ingested: "Đã nạp", failed: "Lỗi nạp" } as const;
const RAG_TONE = { pending: "muted", needs_review: "warn", sent: "warn", ingested: "ok", failed: "bad" } as const;

type Filter = "candidate" | "official" | "rejected" | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "candidate", label: "Chờ duyệt" },
  { key: "official", label: "Đề chính thức" },
  { key: "rejected", label: "Không chọn" },
  { key: "all", label: "Tất cả đề" },
];

const isCandidate = (r: Row) => r.exam.status === "approved" && !r.entry && r.exam.review_status !== "rejected";
const isRejected = (r: Row) => !r.entry && r.exam.review_status === "rejected";
const MATCH: Record<Filter, (r: Row) => boolean> = {
  candidate: isCandidate,
  official: (r) => !!r.entry,
  rejected: isRejected,
  all: () => true,
};

interface Row {
  exam: Exam;
  entry: BankEntry | undefined;
  owner: string;
}

async function loadAll() {
  // API: GET /api/v1/exams (admin: đề nguồn trường), GET /api/v1/bank (admin: cả đề đang ẩn),
  // GET /api/v1/admin/teachers (chỉ để hiện tên người tạo; lỗi thì bỏ qua).
  const [exams, bank, teachers] = await Promise.all([
    api<Exam[]>("/exams"),
    api<BankEntry[]>("/bank"),
    api<User[]>("/admin/teachers").catch(() => [] as User[]),
  ]);
  return { exams, bank, teachers };
}

export default function BankPage() {
  const { data, setData, error, reload } = useLoad(loadAll);
  const [filter, setFilter] = useState<Filter>("candidate");
  const [grade, setGrade] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [choosing, setChoosing] = useState<Exam | null>(null);
  const [removing, setRemoving] = useState<BankEntry | null>(null);
  const [rejecting, setRejecting] = useState<Exam | null>(null);

  const rows = useMemo<Row[]>(() => {
    if (!data) return [];
    const byExam = new Map(data.bank.map((b) => [b.exam_id, b]));
    const names = new Map(data.teachers.map((t) => [t.id, t.full_name]));
    return data.exams.map((exam) => ({ exam, entry: byExam.get(exam.id), owner: names.get(exam.owner_id) ?? "—" }));
  }, [data]);

  const counts = Object.fromEntries(FILTERS.map((f) => [f.key, rows.filter(MATCH[f.key]).length])) as Record<Filter, number>;

  const needle = q.trim().toLowerCase();
  const shown = rows.filter(
    (r) =>
      MATCH[filter](r) &&
      (!grade || String(r.exam.grade) === grade) &&
      (!needle || r.exam.title.toLowerCase().includes(needle) || r.owner.toLowerCase().includes(needle)),
  );

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(errText(err));
    }
    setBusy(false);
  }

  const putEntry = (u: BankEntry) =>
    setData((p) => (p ? { ...p, bank: [u, ...p.bank.filter((x) => x.id !== u.id)] } : p));
  const patchExam = (id: string, patch: Partial<Exam>) =>
    setData((p) => (p ? { ...p, exams: p.exams.map((x) => (x.id === id ? { ...x, ...patch } : x)) } : p));

  const choose = (exam: Exam, visible: boolean) =>
    run(async () => {
      // API: POST /api/v1/bank { exam_id, is_visible }
      putEntry(await api<BankEntry>("/bank", { method: "POST", json: { exam_id: exam.id, is_visible: visible } }));
      patchExam(exam.id, { review_status: "accepted", review_note: null });
    });

  const reject = (exam: Exam, note: string) =>
    run(async () => {
      // API: POST /api/v1/bank/reject { exam_id, note }
      await api("/bank/reject", { method: "POST", json: { exam_id: exam.id, note: note || null } });
      patchExam(exam.id, { review_status: "rejected", review_note: note || null });
    });

  const toggle = (e: BankEntry, visible: boolean) =>
    run(async () => {
      // API: PATCH /api/v1/bank/{id} { is_visible }
      putEntry(await api<BankEntry>(`/bank/${e.id}`, { method: "PATCH", json: { is_visible: visible } }));
    });

  const remove = (e: BankEntry) =>
    run(async () => {
      // API: DELETE /api/v1/bank/{id}
      await api(`/bank/${e.id}`, { method: "DELETE" });
      setData((p) => (p ? { ...p, bank: p.bank.filter((x) => x.id !== e.id) } : p));
      patchExam(e.exam_id, { review_status: "pending", review_note: null });
    });

  return (
    <section>
      <h1 className="mb-1 text-xl font-semibold">Ngân hàng đề</h1>
      <p className="mb-6 text-sm text-muted">
        Giáo viên sinh đề từ dữ liệu của trường và duyệt xong thì đề được gửi về đây. Chọn đề chính thức cho kỳ thi: đề
        chính thức được nạp cho AI học và hiện với giáo viên khi bật “Hiện cho GV”.
      </p>

      {error && <Failed message={error} onRetry={reload} />}
      {!error && !data && <Loading />}
      {data && (
        <>
          <dl className="mb-6 grid grid-cols-2 gap-y-2 border-y border-line py-3 text-sm sm:grid-cols-4">
            <Stat label="Tổng số đề" value={counts.all} />
            <Stat label="Chờ duyệt" value={counts.candidate} />
            <Stat label="Đề chính thức" value={counts.official} />
            <Stat label="Không chọn" value={counts.rejected} />
          </dl>

          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="flex border-b border-line" role="tablist" aria-label="Lọc đề">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  role="tab"
                  aria-selected={filter === f.key}
                  onClick={() => setFilter(f.key)}
                  className={cn(
                    "-mb-px cursor-pointer border-b-2 px-3 pb-2 text-sm",
                    filter === f.key ? "border-accent text-ink" : "border-transparent text-muted",
                  )}
                >
                  {f.label} <span className="text-xs text-muted">({counts[f.key]})</span>
                </button>
              ))}
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-3">
              <Input
                className="w-56"
                type="search"
                placeholder="Tìm theo tên đề, giáo viên"
                aria-label="Tìm theo tên đề, giáo viên"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
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
            </div>
          </div>

          {actionError && (
            <p role="alert" className="mb-3 text-sm text-bad">
              {actionError}
            </p>
          )}

          {shown.length === 0 ? (
            <EmptyState
              title={
                rows.length === 0
                  ? "Trường chưa có đề thi nào"
                  : filter === "candidate" && !needle && !grade
                    ? "Không có đề nào chờ duyệt"
                    : filter === "official" && !needle && !grade
                      ? "Chưa có đề chính thức"
                      : "Không có đề phù hợp"
              }
              hint={
                rows.length === 0
                  ? "Giáo viên sinh đề từ dữ liệu của trường và duyệt xong thì đề sẽ hiện ở đây."
                  : filter === "candidate"
                    ? "Đề giáo viên đã duyệt, chưa được chọn hay từ chối, sẽ hiện ở đây."
                    : "Thử đổi bộ lọc hoặc từ khóa."
              }
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Đề</Th>
                  <Th>Giáo viên</Th>
                  <Th>Lớp</Th>
                  <Th>Trạng thái</Th>
                  <Th>Chính thức</Th>
                  <Th>Hiện cho GV</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {shown.map(({ exam, entry, owner }) => {
                  const s = EXAM_STATUS[exam.status] ?? { label: exam.status, tone: "muted" as ChipTone };
                  return (
                    <tr key={exam.id}>
                      <Td>
                        <Link to={`/exams/${exam.id}`} className="text-accent underline">
                          {exam.title}
                        </Link>
                        <div className="text-xs text-muted">
                          {exam.duration_minutes} phút · tạo {formatTime(exam.created_at)}
                        </div>
                      </Td>
                      <Td>{owner}</Td>
                      <Td>{exam.grade ?? "—"}</Td>
                      <Td>
                        <Chip tone={s.tone}>{s.label}</Chip>
                      </Td>
                      <Td>
                        {entry ? (
                          <>
                            <Chip tone="accent">Chính thức</Chip>
                            <div className="mt-1 flex items-center gap-1 text-xs">
                              <span className="text-muted">AI:</span>
                              <span className={cn(RAG_TONE[entry.rag_status] === "bad" ? "text-bad" : "text-muted")}>
                                {RAG[entry.rag_status]}
                              </span>
                            </div>
                            {entry.error_message && <div className="mt-1 text-xs text-bad">{entry.error_message}</div>}
                          </>
                        ) : exam.review_status === "rejected" ? (
                          <>
                            <Chip tone="bad">Không chọn</Chip>
                            {exam.review_note && <div className="mt-1 max-w-xs text-xs text-muted">{exam.review_note}</div>}
                          </>
                        ) : (
                          <span className="text-sm text-muted">—</span>
                        )}
                      </Td>
                      <Td>
                        {entry ? (
                          <Switch
                            aria-label={`Hiện ${exam.title} cho giáo viên`}
                            checked={entry.is_visible}
                            disabled={busy}
                            onCheckedChange={(v) => toggle(entry, v)}
                          />
                        ) : (
                          <span className="text-sm text-muted">—</span>
                        )}
                      </Td>
                      <Td className="text-right">
                        {entry ? (
                          <Button variant="ghost" className="text-son" disabled={busy} onClick={() => setRemoving(entry)}>
                            Bỏ chính thức
                          </Button>
                        ) : exam.status === "approved" ? (
                          <div className="flex justify-end gap-1">
                            <Button disabled={busy} onClick={() => setChoosing(exam)}>
                              {exam.review_status === "rejected" ? "Chọn lại" : "Chọn làm chính thức"}
                            </Button>
                            {exam.review_status !== "rejected" && (
                              <Button variant="ghost" className="text-son" disabled={busy} onClick={() => setRejecting(exam)}>
                                Không chọn
                              </Button>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-muted">Chờ GV duyệt</span>
                        )}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </>
      )}

      <ChooseDialog
        exam={choosing}
        onClose={() => setChoosing(null)}
        onConfirm={(exam, visible) => {
          setChoosing(null);
          void choose(exam, visible);
        }}
      />
      <RejectDialog
        exam={rejecting}
        onClose={() => setRejecting(null)}
        onConfirm={(exam, note) => {
          setRejecting(null);
          void reject(exam, note);
        }}
      />
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Bỏ đề chính thức?"
        body={`“${removing?.title ?? ""}” sẽ không còn là đề chính thức, bị gỡ khỏi ngân hàng đề và trở lại hàng chờ duyệt. Đề gốc của giáo viên không bị xóa.`}
        confirmLabel="Bỏ chính thức"
        onConfirm={() => removing && remove(removing)}
      />
    </section>
  );
}

function Stat({ label, value }: Readonly<{ label: string; value: number }>) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
    </div>
  );
}

function ChooseDialog({
  exam,
  onClose,
  onConfirm,
}: Readonly<{ exam: Exam | null; onClose: () => void; onConfirm: (exam: Exam, visible: boolean) => void }>) {
  const [visible, setVisible] = useState(true);
  return (
    <Dialog open={!!exam} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Chọn làm đề chính thức">
        <p className="text-sm text-muted">
          “{exam?.title}” sẽ trở thành đề chính thức của trường, được lưu vào ngân hàng đề và nạp cho AI học.
        </p>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <Switch checked={visible} onCheckedChange={setVisible} /> Hiện cho giáo viên ngay
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Hủy</Button>
          </DialogClose>
          <Button onClick={() => exam && onConfirm(exam, visible)}>Xác nhận</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RejectDialog({
  exam,
  onClose,
  onConfirm,
}: Readonly<{ exam: Exam | null; onClose: () => void; onConfirm: (exam: Exam, note: string) => void }>) {
  const [note, setNote] = useState("");
  return (
    <Dialog
      open={!!exam}
      onOpenChange={(o) => {
        if (!o) {
          onClose();
          setNote("");
        }
      }}
    >
      <DialogContent title="Không chọn đề này?">
        <p className="text-sm text-muted">
          “{exam?.title}” sẽ không trở thành đề chính thức. Giáo viên thấy trạng thái và lý do trong mục “Đề của tôi”. Bạn vẫn
          có thể chọn lại sau.
        </p>
        <label className="mt-4 block text-sm">
          <span className="mb-1 block text-muted">Lý do (không bắt buộc)</span>
          <textarea
            className="w-full rounded-sm border border-line bg-surface px-3 py-2 text-sm text-ink"
            rows={3}
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Ví dụ: trùng nhiều câu với đề năm ngoái"
          />
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Hủy</Button>
          </DialogClose>
          <Button
            variant="danger"
            onClick={() => {
              if (exam) onConfirm(exam, note.trim());
              setNote("");
            }}
          >
            Không chọn
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
