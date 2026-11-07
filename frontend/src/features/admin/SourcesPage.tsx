import { PrototypeBanner } from "@/components/PrototypeBanner";
import { useCallback, useEffect, useRef, useState } from "react";

import { Chip, type ChipTone } from "@/components/Chip";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, Td, Th } from "@/components/ui/table";
import { AdminNav, errText, Failed, Field, Loading } from "./shared";
import { createSource, finishIngest, getCoverage, getSources, runCoverageCheck, startIngest } from "./sources/mock";
import type { Coverage, CoverageCheck, Source, SourceStatus } from "./sources/types";

const STATUS: Record<SourceStatus, { label: string; tone: ChipTone }> = {
  loaded: { label: "Đã nạp", tone: "ok" },
  loading: { label: "Đang nạp", tone: "warn" },
  pending: { label: "Chờ nạp", tone: "muted" },
  failed: { label: "Lỗi", tone: "bad" },
};

export default function SourcesPage() {
  const [rows, setRows] = useState<Source[] | null>(null);
  const [cov, setCov] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<CoverageCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [viewing, setViewing] = useState<Source | null>(null);

  const load = useCallback(() => {
    setError(null);
    setRows(null);
    Promise.all([getSources(), getCoverage()]).then(
      ([s, c]) => {
        setRows(s);
        setCov(c);
      },
      (e) => setError(errText(e)),
    );
  }, []);
  useEffect(load, [load]);

  const patch = (s: Source) => setRows((r) => r?.map((x) => (x.id === s.id ? s : x)) ?? null);
  async function ingest(id: string) {
    patch(await startIngest(id));
    patch(await finishIngest(id)); // mock: ingest "completes" a moment later
    setCov(await getCoverage());
  }
  async function runCheck() {
    setChecking(true);
    setCheck(await runCoverageCheck());
    setChecking(false);
  }

  const loaded = rows?.filter((s) => s.status === "loaded").length ?? 0;
  const pct = cov && cov.total ? Math.round((cov.covered / cov.total) * 100) : 0;

  return (
    <section>
      <PrototypeBanner />
      <AdminNav />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Nguồn tài liệu</h1>
        <AddDialog onAdded={(s) => setRows((r) => [...(r ?? []), s])} />
      </div>
      {error && <Failed message={error} onRetry={load} />}
      {!error && !rows && <Loading />}
      {rows && cov && (
        <>
          <dl className="mb-6 grid grid-cols-1 sm:grid-cols-3 border-y border-line py-3 text-sm">
            <Stat label="Số nguồn" value={rows.length} />
            <Stat label="Đã nạp" value={loaded} />
            <Stat label="Độ phủ Bài trong SGK" value={`${pct}%`} />
          </dl>
          {rows.length === 0 ? (
            <EmptyState title="Chưa có nguồn tài liệu" hint="Thêm SGK hoặc đề để RAG có dữ liệu trích dẫn." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Tên</Th>
                  <Th>Loại</Th>
                  <Th>Môn · Lớp</Th>
                  <Th>Chính thức</Th>
                  <Th>Trạng thái</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <Td>{s.name}</Td>
                    <Td>{s.kind === "sgk" ? "SGK" : "Đề"}</Td>
                    <Td>
                      {s.subject} · {s.grade}
                    </Td>
                    <Td>{s.official ? "Có" : "Không"}</Td>
                    <Td>
                      <Chip tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Chip>
                    </Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button variant="ghost" onClick={() => setViewing(s)}>
                          Xem
                        </Button>
                        {s.status === "pending" && (
                          <Button variant="outline" onClick={() => ingest(s.id)}>
                            Nạp
                          </Button>
                        )}
                        {s.status === "failed" && (
                          <Button variant="outline" onClick={() => ingest(s.id)}>
                            Thử lại
                          </Button>
                        )}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          <div className="mt-8 border-t border-line pt-4">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span>
                Độ phủ: {cov.covered}/{cov.total} Bài
              </span>
              <div className="flex items-center gap-3">
                {check && (
                  <Chip tone={check.ok ? "ok" : "warn"}>
                    {check.ok ? "Đủ độ phủ" : `Thiếu ${check.missing} Bài`} · {check.ref}
                  </Chip>
                )}
                <Button variant="outline" disabled={checking} onClick={runCheck}>
                  {checking ? "Đang kiểm tra…" : "Chạy kiểm tra"}
                </Button>
              </div>
            </div>
            <div className="h-2 w-full bg-soft">
              <div className="h-2 bg-accent" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </>
      )}
      <Dialog open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <DialogContent title={viewing?.name ?? ""}>
          {viewing && (
            <p className="text-sm text-muted">
              {viewing.kind === "sgk" ? "SGK" : "Đề"} · {viewing.subject} lớp {viewing.grade} ·{" "}
              {viewing.official ? "Chính thức" : "Không chính thức"} · {STATUS[viewing.status].label}
            </p>
          )}
          <div className="mt-5 flex justify-end">
            <DialogClose asChild>
              <Button variant="outline">Đóng</Button>
            </DialogClose>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function Stat({ label, value }: Readonly<{ label: string; value: string | number }>) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
    </div>
  );
}

function AddDialog({ onAdded }: Readonly<{ onAdded: (s: Source) => void }>) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"sgk" | "de">("sgk");
  const [subject, setSubject] = useState("Toán");
  const [grade, setGrade] = useState(12);
  const [official, setOfficial] = useState(true);
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  async function submit() {
    setBusy(true);
    const s = await createSource({
      name: name.trim(),
      kind,
      subject,
      grade,
      official,
      filename: file.current?.files?.[0]?.name ?? "",
    });
    setBusy(false);
    onAdded(s);
    setOpen(false);
    setName("");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}>Thêm nguồn</Button>
      <DialogContent title="Thêm nguồn tài liệu">
        <Field label="Tên nguồn">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Loại">
            <Select value={kind} onChange={(e) => setKind(e.target.value as "sgk" | "de")}>
              <option value="sgk">SGK</option>
              <option value="de">Đề</option>
            </Select>
          </Field>
          <Field label="Môn">
            <Select value={subject} onChange={(e) => setSubject(e.target.value)}>
              {["Toán", "Lý", "Hóa", "Sinh"].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </Select>
          </Field>
          <Field label="Lớp">
            <Select value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
              {[10, 11, 12].map((g) => (
                <option key={g}>{g}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Tệp tài liệu">
          <input ref={file} type="file" className="text-sm" />
        </Field>
        <label className="mb-3 flex items-center gap-2 text-sm">
          <Switch checked={official} onCheckedChange={setOfficial} /> Nguồn chính thức (Bộ GD&ĐT)
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Hủy</Button>
          </DialogClose>
          <Button disabled={!name.trim() || busy} onClick={submit}>
            Thêm
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
