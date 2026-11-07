import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api";
import { useAction, usePolling } from "@/common";
import { Chip } from "@/components/Chip";
import { Seal } from "@/components/Seal";
import { Stepper } from "@/components/Stepper";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PART_OF_TYPE, TYPE_LABEL, type Exam, type Question } from "@/types";

import { cellLabel, FormError, PAPER_FONT, PART_HEAD, PARTS, StatusChip, teacherSteps, useMatrixCells } from "./lib";
import QuestionPanel from "./QuestionPanel";

type Check = { bieu_thuc?: string; gia_tri?: number | string; lam_tron?: number | null };

// BE chỉ trả mã đoạn tài liệu (hash, không đọc được): hiện nhãn đánh số, giữ mã gốc ở tooltip.
function citationId(c: unknown): string {
  if (typeof c === "string") return c;
  if (c && typeof c === "object") {
    const o = c as Record<string, unknown>;
    const v = o.id ?? o.chunk_id;
    if (typeof v === "string") return v;
  }
  return "";
}

export default function ExamReviewPage() {
  const { id } = useParams();
  const [exam, setExam] = useState<Exam | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [seen, setSeen] = useState<Set<string>>(() => new Set());
  const [showKey, setShowKey] = useState(true);
  const [solutionsOpen, setSolutionsOpen] = useState(false);
  const docRef = useRef<HTMLDivElement>(null);
  const loader = useAction();
  const action = useAction();

  const load = useCallback(() => {
    // API: GET /api/v1/exams/{id}
    void loader.run(async () => setExam(await api<Exam>(`/exams/${id}`)));
  }, [id]);
  useEffect(load, [load]);
  const generating = exam?.status === "generating";
  usePolling(load, generating);
  const cells = useMatrixCells(exam?.matrix_id);

  const partOf = (q: Question) => q.part || PART_OF_TYPE[q.content.type];
  const sorted = exam ? [...exam.questions].sort((a, b) => a.position - b.position) : [];
  const idsKey = sorted.map((q) => q.id).join(",");

  const markActive = useCallback((qid: string) => {
    setActive(qid);
    setSeen((prev) => (prev.has(qid) ? prev : new Set(prev).add(qid)));
  }, []);

  // The first question is open on arrival, so it counts as read.
  useEffect(() => {
    if (!active && sorted[0]) markActive(sorted[0].id);
  }, [idsKey]);

  // Scroll spy: the question crossing the upper third of the viewport is the active one.
  useEffect(() => {
    const root = docRef.current;
    if (!root) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const en of entries) if (en.isIntersecting) markActive((en.target as HTMLElement).dataset.qid!);
      },
      { rootMargin: "-25% 0px -65% 0px" },
    );
    root.querySelectorAll<HTMLElement>("[data-qid]").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [idsKey, markActive]);

  const head = (
    <>
      <Stepper steps={teacherSteps({ matrix: exam?.matrix_id, exam: id })} current={3} />
      <p className="text-xs uppercase tracking-wider text-muted">Bước 4 trên 5 · Duyệt đề</p>
      <h1 className="mb-1 text-2xl font-semibold">{exam ? exam.title : "Duyệt đề"}</h1>
    </>
  );

  if (!exam) {
    return (
      <section>
        {head}
        {loader.error ? <ErrorState message="Không tải được đề." onRetry={load} /> : <p className="py-6 text-sm text-muted">Đang tải…</p>}
      </section>
    );
  }

  const locked = exam.status === "approved" || generating;
  const byCell = new Map<string, number>();
  for (const q of exam.questions) byCell.set(q.matrix_cell_id, (byCell.get(q.matrix_cell_id) ?? 0) + 1);
  const missing = exam.cell_runs
    .map((run) => ({ run, have: byCell.get(run.matrix_cell_id) ?? 0 }))
    .filter(({ run, have }) => have < run.question_count);

  const numbered = new Map<string, number>(); // question id -> number within its part
  for (const p of PARTS) sorted.filter((q) => partOf(q) === p.part).forEach((q, i) => numbered.set(q.id, i + 1));

  const current = sorted.find((q) => q.id === active) ?? sorted[0];

  function goTo(qid: string) {
    markActive(qid);
    document.querySelector(`[data-qid="${qid}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  async function fill(cellId: string) {
    // API: POST /api/v1/exams/{id}/cells/{cell_id}/fill (một lần bù đủ số câu thiếu, hỏi RAG lại tối đa 3 lượt)
    if (await action.run(() => api(`/exams/${id}/cells/${cellId}/fill`, { method: "POST" }))) load();
  }

  async function approve() {
    // API: POST /api/v1/exams/{id}/approve
    const approved = await action.run(() => api<Exam>(`/exams/${id}/approve`, { method: "POST" }));
    if (approved) setExam(approved);
  }

  const citations = (current?.content.citations ?? []) as unknown[];
  const check = current?.content.check as Check | null | undefined;
  const currentCell = current ? cells[current.matrix_cell_id] : undefined;

  return (
    <section>
      {head}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="flex flex-wrap items-center gap-3 text-sm text-muted">
          <StatusChip status={exam.status} />
          {exam.duration_minutes} phút · {exam.questions.length} câu ·
          <Link to={`/matrices/${exam.matrix_id}`} className="text-accent">
            xem ma trận
          </Link>
          {exam.status === "approved" && <Seal />}
        </p>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="inline-flex cursor-pointer items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-accent" checked={showKey} onChange={(e) => setShowKey(e.target.checked)} />
            Hiện đáp án
          </label>
          <Button
            variant="outline"
            className="h-8"
            onClick={() => {
              setShowKey(true);
              setSolutionsOpen((v) => !v);
            }}
          >
            {solutionsOpen ? "Thu gọn lời giải" : "Mở tất cả lời giải"}
          </Button>
        </div>
      </div>

      {generating && (
        <p className="mb-4 text-sm text-muted">
          Đang sinh câu hỏi: {exam.cells_done}/{exam.cells_total} ô…{" "}
          <Link to={`/exams?exam=${exam.id}`} className="text-accent">
            xem tiến trình
          </Link>
        </p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[12.5rem_minmax(0,1fr)] xl:grid-cols-[12.5rem_minmax(0,1fr)_16rem]">
        <nav aria-label="Danh sách câu" className="sticky top-0 z-10 -mx-1 space-y-4 bg-paper px-1 py-2 text-sm lg:top-4 lg:mx-0 lg:bg-transparent lg:px-0 lg:py-0">
          {PARTS.map(({ part, type }) => {
            const qs = sorted.filter((q) => partOf(q) === part);
            const gaps = missing.filter(({ run }) => cells[run.matrix_cell_id]?.type === type);
            if (qs.length === 0 && gaps.length === 0) return null;
            return (
              <div key={part}>
                <h2 className="mb-1.5 font-medium">
                  Phần {part} <span className="font-normal text-muted">· {TYPE_LABEL[type]}</span>
                </h2>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(2.1rem,1fr))] gap-1.5">
                  {qs.map((q) => {
                    const isCur = q.id === current?.id;
                    return (
                      <button
                        key={q.id}
                        type="button"
                        aria-label={`Câu ${numbered.get(q.id)} phần ${part}`}
                        aria-current={isCur ? "true" : undefined}
                        onClick={() => goTo(q.id)}
                        className={cn(
                          "relative h-8 cursor-pointer rounded-sm border text-xs tabular-nums",
                          isCur ? "border-accent bg-accent text-surface" : seen.has(q.id) ? "border-line bg-soft text-muted" : "border-line bg-surface hover:border-accent",
                        )}
                      >
                        {numbered.get(q.id)}
                        {q.edited && <i className={cn("absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full", isCur ? "bg-surface" : "bg-accent")} />}
                      </button>
                    );
                  })}
                  {gaps.flatMap(({ run, have }) =>
                    Array.from({ length: run.question_count - have }, (_, k) => (
                      <button
                        key={`${run.matrix_cell_id}-${k}`}
                        type="button"
                        aria-label={`Câu thiếu ở ô ${run.sort_order}`}
                        onClick={() => document.getElementById(`missing-${run.matrix_cell_id}`)?.scrollIntoView({ block: "center", behavior: "smooth" })}
                        className="h-8 cursor-pointer rounded-sm border border-dashed border-bad text-xs text-bad"
                      >
                        ?
                      </button>
                    )),
                  )}
                </div>
              </div>
            );
          })}
          <div className="hidden space-y-1.5 border-t border-line pt-3 text-xs text-muted lg:block">
            <p>
              Đã đọc qua {seen.size}/{sorted.length} câu
            </p>
            <div className="h-1.5 overflow-hidden rounded-full bg-soft">
              <div className="h-full bg-accent" style={{ width: `${(seen.size / Math.max(1, sorted.length)) * 100}%` }} />
            </div>
            <p className="flex items-center gap-1.5 pt-1">
              <i className="h-1.5 w-1.5 rounded-full bg-accent" /> GV đã sửa
            </p>
            <p className="flex items-center gap-1.5">
              <i className="h-1.5 w-1.5 rounded-full border border-dashed border-bad" /> Câu còn thiếu
            </p>
          </div>
        </nav>

        <div ref={docRef} className={cn("min-w-0 rounded-sm border border-line bg-surface px-5 py-6 text-[17px] leading-relaxed sm:px-9", PAPER_FONT)}>
          <div className="mb-2 border-b border-line pb-4 text-center">
            <p className="text-lg font-bold uppercase">{exam.title}</p>
            <p className="text-[15px] italic text-muted">Thời gian làm bài {exam.duration_minutes} phút</p>
          </div>
          {sorted.length === 0 && <p className="py-6 font-sans text-sm text-muted">{generating ? "Chưa có câu nào, đang sinh…" : "Đề chưa có câu nào."}</p>}
          {PARTS.map(({ part, type }) => {
            const qs = sorted.filter((q) => partOf(q) === part);
            if (qs.length === 0) return null;
            return (
              <div key={part}>
                <p className="mt-6 mb-1 font-bold">
                  {PART_HEAD[type][0]} <span className="block text-[15px] font-normal italic text-muted">{PART_HEAD[type][1]}</span>
                </p>
                {qs.map((q) => (
                  <div
                    key={q.id}
                    data-qid={q.id}
                    onClick={() => markActive(q.id)}
                    className={cn(
                      "-mx-3 scroll-mt-20 rounded-sm border px-3 py-3 lg:scroll-mt-4",
                      q.id === current?.id ? "border-accent/30 bg-paper/40" : "border-transparent hover:border-line",
                    )}
                  >
                    <QuestionPanel
                      examId={exam.id}
                      question={q}
                      number={numbered.get(q.id) ?? 1}
                      locked={locked}
                      showKey={showKey}
                      solutionsOpen={solutionsOpen}
                      active={q.id === current?.id}
                      onChanged={load}
                    />
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        <aside className="space-y-5 text-sm lg:col-start-2 xl:sticky xl:top-4 xl:col-start-auto" aria-live="polite">
          {current && (
            <div className="space-y-1.5 border-t border-ink pt-2.5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                Câu {numbered.get(current.id)} · Phần {partOf(current)}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                <Chip>{TYPE_LABEL[current.content.type]}</Chip>
                <Chip>{current.content.level}</Chip>
              </div>
              {currentCell && <p className="text-xs text-muted">{cellLabel(currentCell, currentCell.sort_order)}</p>}
            </div>
          )}
          <div className="space-y-1.5 border-t border-ink pt-2.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Kiểm tra đáp án</h3>
            {check ? (
              <dl className="space-y-1">
                <div>
                  <dt className="text-muted">Biểu thức</dt>
                  <dd className="break-words font-mono text-xs">{check.bieu_thuc ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted">Giá trị</dt>
                  <dd className="text-ok">✓ {String(check.gia_tri ?? "—")}</dd>
                </div>
              </dl>
            ) : (
              <p className="text-muted">Câu này không có biểu thức cần kiểm.</p>
            )}
          </div>
          <div className="space-y-1.5 border-t border-ink pt-2.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Nguồn trích dẫn</h3>
            {citations.length === 0 ? (
              <p className="text-muted">Câu này chưa có trích dẫn.</p>
            ) : (
              <ul>
                {citations.map((c, i) => (
                  <li key={i} className="break-words border-b border-line py-1.5 text-muted last:border-b-0" title={citationId(c) || undefined}>
                    Nguồn SGK {i + 1}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>

      {!generating && missing.length > 0 && (
        <ul className="mt-6 border-l-2 border-warn pl-4 text-sm">
          <li className="font-medium text-warn">Các ô còn thiếu câu (phải đủ mới duyệt được)</li>
          {missing.map(({ run, have }) => (
            <li key={run.matrix_cell_id} id={`missing-${run.matrix_cell_id}`} className="mt-1 flex scroll-mt-24 flex-wrap items-center gap-2">
              <span>
                {cellLabel(cells[run.matrix_cell_id], run.sort_order)}: có {have}/{run.question_count}
              </span>
              {exam.status !== "approved" && (
                <Button variant="outline" disabled={action.busy} onClick={() => fill(run.matrix_cell_id)}>
                  Bù {run.question_count - have} câu
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <FormError error={action.error} />

      <div className="sticky bottom-0 z-10 mt-6 flex flex-wrap items-center gap-3 rounded-sm border border-line bg-surface px-4 py-3 text-sm">
        {exam.status === "approved" ? (
          <>
            <span className="text-muted">Đề đã duyệt và được khoá.</span>
            <Link to={`/exams/${exam.id}/export`} className="ml-auto inline-flex h-9 items-center rounded-sm border border-accent bg-accent px-3 font-medium text-surface">
              Sang bước Xuất đề →
            </Link>
          </>
        ) : (
          <>
            <span className="tabular-nums">
              Đã đọc qua <b>{seen.size}/{sorted.length}</b> câu
              {missing.length > 0 && <span className="text-warn"> · {missing.length} ô còn thiếu câu</span>}
            </span>
            <span className="ml-auto text-xs text-muted">Sửa / sinh lại / xoá ngay trên từng câu. Duyệt xong đề bị khoá.</span>
            <Button onClick={approve} disabled={generating || missing.length > 0 || action.busy}>
              Duyệt đề
            </Button>
          </>
        )}
      </div>
    </section>
  );
}
