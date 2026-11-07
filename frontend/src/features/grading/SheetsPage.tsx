import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PrototypeBanner } from "@/components/PrototypeBanner";
import { EmptyState } from "@/components/states";
import { GRADING_STEPS, Stepper } from "@/components/Stepper";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";

import { createSheets, getApprovedExams, getClasses, getSheets, QUESTION_COUNT } from "./mock";
import type { AnswerSheet } from "./types";
import { Gate, useLoad } from "./useLoad";

const corner = "absolute h-3 w-3 bg-ink";

/** A4-like answer sheet preview: corner markers, Phần I bubbles, placeholder lines for Phần II/III. */
function SheetPreview({ sheet }: Readonly<{ sheet: AnswerSheet }>) {
  return (
    <div className="relative mx-auto aspect-[210/297] w-full max-w-sm border border-line bg-surface p-8 text-xs" aria-label="Xem trước phiếu trả lời">
      <span className={`${corner} left-2 top-2`} />
      <span className={`${corner} right-2 top-2`} />
      <span className={`${corner} bottom-2 left-2`} />
      <span className={`${corner} bottom-2 right-2`} />
      <p className="text-center font-semibold">PHIẾU TRẢ LỜI · Lớp {sheet.className} · Mã đề {sheet.code}</p>
      <p className="mb-3 mt-1 text-center text-muted">{sheet.examTitle}</p>
      <p className="mb-1 font-medium">Phần I</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {Array.from({ length: QUESTION_COUNT }, (_, i) => (
          <div key={i} className="flex items-center gap-1">
            <span className="w-5 text-right text-muted">{i + 1}</span>
            {["A", "B", "C", "D"].map((l) => (
              <span key={l} className="flex h-4 w-4 items-center justify-center rounded-full border border-ink text-[9px]">{l}</span>
            ))}
          </div>
        ))}
      </div>
      {["Phần II", "Phần III"].map((p) => (
        <div key={p} className="mt-4">
          <p className="mb-1 font-medium">{p}</p>
          {[0, 1, 2].map((n) => <div key={n} className="mb-2 h-px bg-line" />)}
        </div>
      ))}
    </div>
  );
}

export function SheetsPage() {
  const [params] = useSearchParams();
  const exams = useLoad(getApprovedExams, []);
  const classes = useLoad(getClasses, []);
  const sheets = useLoad(getSheets, []);
  const [examId, setExamId] = useState("");
  const [classId, setClassId] = useState(params.get("class") ?? "");
  const [versions, setVersions] = useState(2);
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState(0);

  const loading = exams.loading || classes.loading || sheets.loading;
  const error = exams.error || classes.error || sheets.error;
  const reload = () => { exams.reload(); classes.reload(); sheets.reload(); };
  const list = sheets.data ?? [];

  const create = async () => {
    setBusy(true);
    await createSheets(examId, classId, versions);
    setShown(0);
    sheets.reload();
    setBusy(false);
  };

  return (
    <section>
      <PrototypeBanner />
      <Stepper steps={GRADING_STEPS} current={1} />
      <h1 className="mb-4 text-xl font-semibold">Phiếu trả lời</h1>
      <Gate loading={loading} error={error} reload={reload} hasData={!!(exams.data && classes.data)} />
      {exams.data && classes.data && classes.data.length === 0 && (
        <EmptyState title="Chưa có lớp để tạo phiếu" hint="Tạo lớp và nhập học sinh trước.">
          <Link to="/classes" className="text-accent underline">Đến Lớp và học sinh</Link>
        </EmptyState>
      )}
      {exams.data && classes.data && classes.data.length > 0 && (
        <div className="grid gap-8 md:grid-cols-[18rem_1fr]">
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void create(); }}>
            <label className="block text-sm">Đề đã duyệt
              <Select className="mt-1" value={examId} onChange={(e) => setExamId(e.target.value)}>
                <option value="">Chọn đề…</option>
                {exams.data.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
              </Select>
            </label>
            <label className="block text-sm">Lớp
              <Select className="mt-1" value={classId} onChange={(e) => setClassId(e.target.value)}>
                <option value="">Chọn lớp…</option>
                {classes.data.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </Select>
            </label>
            <label className="block text-sm">Số mã đề
              <Select className="mt-1" value={versions} onChange={(e) => setVersions(Number(e.target.value))}>
                {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>
            </label>
            <Button type="submit" disabled={!examId || !classId || busy}>Tạo phiếu</Button>
          </form>
          <div>
            {list.length === 0 ? (
              <EmptyState title="Chưa có phiếu nào" hint="Chọn đề, lớp rồi bấm “Tạo phiếu”." />
            ) : (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                  {list.map((s, i) => (
                    <button key={s.id} type="button" onClick={() => setShown(i)} className={`cursor-pointer border-b-2 px-2 py-1 ${i === shown ? "border-accent font-semibold text-accent" : "border-transparent text-muted"}`}>
                      Mã đề {s.code}
                    </button>
                  ))}
                </div>
                <SheetPreview sheet={list[Math.min(shown, list.length - 1)]} />
                <div className="mt-4 flex items-center gap-3">
                  {/* TODO(BE): GET /api/v1/answer-sheets/{id}/pdf
                      req : none
                      res : application/pdf (A4, corner markers, bubbles)  (proposed contract)
                      owner: Backend (Huy/Phu) · feature: Khối 2 · now: button disabled (no mock) */}
                  <Button variant="outline" disabled title="Chưa có API tạo PDF">Tải PDF</Button>
                  <Link to="/scans" className="inline-flex h-9 items-center rounded-sm border border-accent bg-accent px-3 text-sm font-medium text-surface">Tiếp tục</Link>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
