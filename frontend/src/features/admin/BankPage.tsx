import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, Td, Th } from "@/components/ui/table";
import type { BankEntry, Exam } from "@/types";
import { AdminNav, ConfirmDialog, errText, Failed, Loading, useLoad } from "./shared";

const RAG = { pending: "Chờ nạp", needs_review: "Chờ duyệt", sent: "Đã gửi", ingested: "Đã nạp", failed: "Lỗi" } as const;
const RAG_TONE = { pending: "muted", needs_review: "warn", sent: "warn", ingested: "ok", failed: "bad" } as const;

export default function BankPage() {
  // API: GET /api/v1/bank (admin sees hidden entries too)
  const { data, setData, error, reload } = useLoad(() => api<BankEntry[]>("/bank"));
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<BankEntry | null>(null);

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

  const toggle = (e: BankEntry, visible: boolean) =>
    run(async () => {
      // API: PATCH /api/v1/bank/{id} { is_visible }
      const u = await api<BankEntry>(`/bank/${e.id}`, { method: "PATCH", json: { is_visible: visible } });
      setData((p) => p?.map((x) => (x.id === u.id ? u : x)) ?? null);
    });

  const remove = (e: BankEntry) =>
    run(async () => {
      // API: DELETE /api/v1/bank/{id}
      await api(`/bank/${e.id}`, { method: "DELETE" });
      setData((p) => p?.filter((x) => x.id !== e.id) ?? null);
    });

  return (
    <section>
      <AdminNav />
      <div className="mb-1 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Ngân hàng đề</h1>
        <AddToBank taken={new Set(data?.map((e) => e.exam_id))} onAdded={reload} />
      </div>
      <p className="mb-4 text-sm text-muted">Bật “Hiện” để giáo viên thấy đề trong ngân hàng.</p>
      {actionError && (
        <p role="alert" className="mb-3 text-sm text-bad">
          {actionError}
        </p>
      )}
      {error && <Failed message={error} onRetry={reload} />}
      {!error && !data && <Loading />}
      {data?.length === 0 && (
        <EmptyState title="Ngân hàng trống" hint="Mở một đề đã duyệt và bấm “Nạp vào ngân hàng đề”.">
          <Link to="/exams" className="text-accent underline">
            Đến danh sách đề
          </Link>
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>Đề</Th>
              <Th>Lớp</Th>
              <Th>RAG</Th>
              <Th>Hiện cho GV</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id}>
                <Td>
                  <Link to={`/exams/${e.exam_id}`} className="text-accent underline">
                    {e.title}
                  </Link>
                  <div className="text-xs text-muted">
                    {e.subject} · {e.duration_minutes} phút · {e.saved_by.full_name}
                  </div>
                </Td>
                <Td>{e.grade}</Td>
                <Td>
                  <Chip tone={RAG_TONE[e.rag_status]}>{RAG[e.rag_status]}</Chip>
                  {e.error_message && <div className="mt-1 text-xs text-bad">{e.error_message}</div>}
                </Td>
                <Td>
                  <Switch
                    aria-label={`Hiện ${e.title} cho giáo viên`}
                    checked={e.is_visible}
                    disabled={busy}
                    onCheckedChange={(v) => toggle(e, v)}
                  />
                </Td>
                <Td className="text-right">
                  <Button variant="ghost" className="text-son" disabled={busy} onClick={() => setRemoving(e)}>
                    Gỡ
                  </Button>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Gỡ đề khỏi ngân hàng?"
        body={`“${removing?.title ?? ""}” sẽ bị gỡ khỏi ngân hàng đề. Đề gốc không bị xóa.`}
        confirmLabel="Gỡ"
        onConfirm={() => removing && remove(removing)}
      />
    </section>
  );
}

function AddToBank({ taken, onAdded }: Readonly<{ taken: Set<string>; onAdded: () => void }>) {
  const [open, setOpen] = useState(false);
  const [exams, setExams] = useState<Exam[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [examId, setExamId] = useState("");
  const [visible, setVisible] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    setExams(null);
    setLoadError(null);
    // API: GET /api/v1/exams (admin gets every exam in the school; no status filter, so filter approved here)
    api<Exam[]>("/exams").then(setExams, (e) => setLoadError(errText(e)));
  }
  useEffect(() => {
    if (open) {
      setExamId("");
      setErr(null);
      load();
    }
  }, [open]);

  const choices = exams?.filter((e) => e.status === "approved" && !taken.has(e.id));

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      // API: POST /api/v1/bank { exam_id, is_visible }
      await api("/bank", { method: "POST", json: { exam_id: examId, is_visible: visible } });
      setOpen(false);
      onAdded();
    } catch (e) {
      setErr(errText(e));
    }
    setBusy(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}>Nạp đề vào ngân hàng</Button>
      <DialogContent title="Nạp đề vào ngân hàng">
        {loadError && <Failed message={loadError} onRetry={load} />}
        {!loadError && !choices && <Loading />}
        {choices?.length === 0 && (
          <EmptyState title="Không có đề đã duyệt để nạp" hint="Duyệt một đề trước, hoặc các đề đã duyệt đều đã ở trong ngân hàng." />
        )}
        {choices && choices.length > 0 && (
          <>
            <Select aria-label="Chọn đề" value={examId} onChange={(e) => setExamId(e.target.value)}>
              <option value="">Chọn đề đã duyệt…</option>
              {choices.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.title}
                </option>
              ))}
            </Select>
            <label className="mt-3 flex items-center gap-2 text-sm">
              <Switch checked={visible} onCheckedChange={setVisible} /> Hiện cho giáo viên ngay
            </label>
          </>
        )}
        {err && (
          <p role="alert" className="mt-3 text-sm text-bad">
            {err}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Hủy</Button>
          </DialogClose>
          <Button disabled={!examId || busy} onClick={submit}>
            Nạp
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
