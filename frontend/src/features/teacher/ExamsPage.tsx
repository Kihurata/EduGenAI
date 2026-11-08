import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, ApiError } from "@/api";
import { formatTime, useAction, usePolling } from "@/common";
import { Chip } from "@/components/Chip";
import { Stepper } from "@/components/Stepper";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { TYPE_LABEL, type Cell, type CellRun, type Exam } from "@/types";

import { PARTS, StatusChip, teacherSteps, useMatrixCells } from "./lib";

type CellState = "wait" | "run" | "done" | "short" | "error";

interface CellRow {
  cell: Cell;
  run?: CellRun;
  state: CellState;
  done: number; // questions known to be done (exact once the run is recorded)
}

/**
 * BE generates cells one by one in sort order and only bumps `cells_done` while running;
 * per-cell results (`cell_runs`) are written when the whole exam finishes.
 */
function cellRows(exam: Exam, cells: Cell[]): CellRow[] {
  return cells.map((cell, i) => {
    const run = exam.cell_runs.find((r) => r.matrix_cell_id === cell.id);
    if (run) {
      const state: CellState = run.status === "complete" ? "done" : run.status === "short" ? "short" : "error";
      return { cell, run, state, done: run.valid_count };
    }
    if (exam.status === "generating") {
      if (i < exam.cells_done) return { cell, state: "done", done: cell.count };
      return { cell, state: i === exam.cells_done ? "run" : "wait", done: 0 };
    }
    return { cell, state: "error", done: 0 };
  });
}

/**
 * What the teacher sees. RAG misses (short / error cells) are not the teacher's concern: the page
 * re-fills them by itself, so they show as waiting or generating, never as an error.
 */
type ViewState = "wait" | "run" | "done";

const STATE_CHIP: Record<ViewState, [string, "ok" | "accent" | "muted"]> = {
  done: ["Đã sinh", "ok"],
  run: ["Đang sinh", "accent"],
  wait: ["Chờ", "muted"],
};

/**
 * Automatic re-fills per cell before the page falls back to a manual "Sinh lại" button. One is
 * enough: each fill already asks RAG up to FILL_ROUNDS (3) times on the BE, and every round costs
 * an LLM call.
 */
const AUTO_RETRIES = 1;
/** Ceiling on automatic re-fills for one exam while the page is open, whatever the number of cells. */
const AUTO_FILLS_PER_EXAM = 6;

/** A failed fill request (network, server, expired login), as opposed to RAG returning too few questions. */
function requestProblem(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError && error.status === 409) return null; // the exam started generating meanwhile
  return "Không kết nối được máy chủ nên chưa sinh bù được. Kiểm tra mạng rồi bấm “Sinh lại”.";
}

const isBad = (r: CellRow) => r.state === "short" || r.state === "error";

export default function ExamsPage() {
  const [items, setItems] = useState<Exam[] | null>(null);
  const [params, setParams] = useSearchParams();
  const [hlCell, setHlCell] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null); // cell being re-filled
  const attempts = useRef<Record<string, number>>({}); // "examId:cellId" → auto re-fills sent
  const list = useAction();
  const fill = useAction();

  const load = useCallback(() => {
    // API: GET /api/v1/exams
    void list.run(async () => setItems(await api<Exam[]>("/exams")));
  }, []);
  useEffect(load, [load]);
  usePolling(load, !!items?.some((e) => e.status === "generating"));

  const selected = items?.find((e) => e.id === params.get("exam")) ?? items?.[0];
  const cellMap = useMatrixCells(selected?.matrix_id);
  const cells = Object.values(cellMap).sort((a, b) => a.sort_order - b.sort_order);

  async function retry(examId: string, cellId: string) {
    setRetrying(cellId);
    // API: POST /api/v1/exams/{id}/cells/{cell_id}/fill (errors stay silent: the next pass retries)
    await fill.run(() => api(`/exams/${examId}/cells/${cellId}/fill`, { method: "POST" }));
    load();
  }

  const rows = selected ? cellRows(selected, cells) : [];
  const problem = requestProblem(fill.error);
  const examFills = selected ? (attempts.current[selected.id] ?? 0) : 0;
  // A failed request stops the automatic loop (no burning calls while offline); the teacher retries by hand.
  const retriesLeft = (r: CellRow) =>
    !!selected && !problem && examFills < AUTO_FILLS_PER_EXAM && (attempts.current[`${selected.id}:${r.cell.id}`] ?? 0) < AUTO_RETRIES;
  const canFill = !!selected && selected.status !== "generating" && selected.status !== "approved";
  const badCells = rows.filter(isBad).map((r) => r.cell.id).join(",");

  // Auto re-fill: once the exam is idle, re-fill the first short / failed cell that still has tries left.
  // Counters are bumped before the request so a re-render can never send the same fill twice.
  useEffect(() => {
    if (!selected || !canFill || fill.busy || !badCells) return;
    const target = rows.find((r) => isBad(r) && retriesLeft(r));
    if (!target) return;
    const key = `${selected.id}:${target.cell.id}`;
    attempts.current[key] = (attempts.current[key] ?? 0) + 1;
    attempts.current[selected.id] = (attempts.current[selected.id] ?? 0) + 1;
    void retry(selected.id, target.cell.id);
    // rows / helpers are rebuilt every render; the exam, its status, its bad cells and request errors drive this
  }, [selected?.id, selected?.status, badCells, canFill, fill.busy, problem]);

  const generating = selected?.status === "generating";
  const autoPending = rows.some((r) => isBad(r) && retriesLeft(r));
  const view: ViewRow[] = rows.map((r) => {
    if (!isBad(r)) return { ...r, view: r.state as ViewState, manual: false };
    const active = r.cell.id === retrying && (generating || fill.busy);
    return { ...r, view: active ? "run" : "wait", manual: canFill && !fill.busy && !retriesLeft(r) };
  });

  function jumpTo(cellId: string) {
    setHlCell(cellId);
    document.getElementById(`cell-${cellId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  return (
    <section>
      <Stepper steps={teacherSteps({ matrix: selected?.matrix_id, exam: selected?.id })} current={2} />
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wider text-muted">Bước 3 trên 5 · Sinh đề</p>
          <h1 className="text-2xl font-semibold">{selected?.title ?? "Sinh đề"}</h1>
          {selected && (
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
              {selected.status === "generated" || selected.status === "approved" ? (
                <StatusChip status={selected.status} />
              ) : (
                <Chip tone={generating || autoPending ? "accent" : "muted"}>{generating || autoPending ? "Đang sinh" : "Chưa đủ câu"}</Chip>
              )}
              {selected.duration_minutes} phút · tạo lúc {formatTime(selected.created_at)} ·
              <Link to={`/matrices/${selected.matrix_id}`} className="text-accent">
                xem ma trận
              </Link>
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-4 text-sm">
          {items && items.length > 1 && (
            <label>
              <span className="mb-1 block text-xs text-muted">Đề khác</span>
              <Select className="w-72 max-w-full" value={selected?.id} onChange={(e) => setParams({ exam: e.target.value })}>
                {items.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.title} · {formatTime(e.created_at)}
                  </option>
                ))}
              </Select>
            </label>
          )}
          <Link to="/matrices" className="pb-2 text-accent">
            + Sinh đề từ ma trận khác
          </Link>
        </div>
      </div>

      {list.error && !items ? (
        <ErrorState message="Không tải được danh sách đề." onRetry={load} />
      ) : !items ? (
        <p className="py-6 text-sm text-muted">Đang tải…</p>
      ) : !selected ? (
        <EmptyState title="Chưa có đề nào" hint="Xác nhận một ma trận rồi bấm “Sinh đề”.">
          <Link to="/matrices" className="text-accent underline">
            Đến bước Ma trận
          </Link>
        </EmptyState>
      ) : cells.length === 0 ? (
        <p className="py-6 text-sm text-muted">Đang tải các ô của ma trận…</p>
      ) : (
        <>
          <Summary exam={selected} rows={view} working={generating || fill.busy || autoPending} />
          {problem && (
            <p role="alert" className="mt-3 rounded-sm border border-warn/40 bg-warn/10 px-4 py-2 text-sm text-warn">
              {problem}
            </p>
          )}
          <div className="mt-6 grid items-start gap-8 lg:grid-cols-[18rem_minmax(0,1fr)]">
            <SlotMap rows={view} hl={hlCell} onPick={jumpTo} />
            <CellList rows={view} hl={hlCell} busy={fill.busy} onRetry={(cellId) => retry(selected.id, cellId)} />
          </div>
        </>
      )}
    </section>
  );
}

interface ViewRow extends CellRow {
  view: ViewState;
  manual: boolean; // automatic re-fills used up: offer a manual "Sinh lại"
}

function Summary({ exam, rows, working }: Readonly<{ exam: Exam; rows: ViewRow[]; working: boolean }>) {
  const need = rows.reduce((s, r) => s + r.cell.count, 0);
  const generating = exam.status === "generating";
  const doneCells = rows.filter((r) => r.view === "done").length;
  const pct = generating ? (exam.cells_done / Math.max(1, exam.cells_total)) * 100 : (exam.questions.length / Math.max(1, need)) * 100;
  const complete = exam.status === "generated" || exam.status === "approved";
  return (
    <div className="space-y-3 rounded-sm border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-2xl font-semibold tabular-nums">
          {generating ? `${exam.cells_done}/${exam.cells_total} ô` : `${exam.questions.length}/${need} câu`}
          <span className="ml-2 text-sm font-normal text-muted">
            {generating ? `đã xong · đề cần ${need} câu` : `${doneCells}/${rows.length} ô ma trận đủ câu`}
          </span>
        </p>
        <span className="text-sm text-muted">{complete ? "Đã chạy xong" : working ? `Đang sinh · ${Math.round(pct)}%` : "Đang chờ"}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-soft">
        <div className={cn("h-full", complete ? "bg-ok" : "bg-accent")} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <div className="flex flex-wrap gap-4 text-xs text-muted">
        <Legend cls="border-line bg-surface" label="Chờ" />
        <Legend cls="animate-pulse border-accent bg-accent/30" label="Đang sinh" />
        <Legend cls="border-ok bg-ok" label="Đã sinh" />
      </div>
      {exam.status === "approved" ? (
        <Banner text="Đề đã duyệt.">
          <Link to={`/exams/${exam.id}/export`} className="font-medium text-accent">
            Sang bước Xuất đề →
          </Link>
        </Banner>
      ) : exam.status === "generated" ? (
        <Banner text={`✓ Đã sinh đủ ${need} câu. Mọi câu đã qua bước kiểm đáp án.`}>
          <Link to={`/exams/${exam.id}`} className="inline-flex h-9 items-center rounded-sm border border-accent bg-accent px-3 font-medium text-surface">
            Sang bước Duyệt →
          </Link>
        </Banner>
      ) : null}
    </div>
  );
}

function Legend({ cls, label }: Readonly<{ cls: string; label: string }>) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <i className={cn("inline-block h-3 w-3 rounded-[3px] border", cls)} />
      {label}
    </span>
  );
}

function Banner({ text, children }: Readonly<{ text: string; children: ReactNode }>) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-sm border border-ok/40 bg-ok/10 px-4 py-2.5 text-sm text-ok">
      <span className="flex-1">{text}</span>
      {children}
    </div>
  );
}

/** One square per question of the exam, grouped by part, coloured by the state of its matrix cell. */
function SlotMap({ rows, hl, onPick }: Readonly<{ rows: ViewRow[]; hl: string | null; onPick: (cellId: string) => void }>) {
  const counts = { done: 0, run: 0, wait: 0 };
  for (const r of rows) counts[r.view]++;
  return (
    <aside className="space-y-5 lg:sticky lg:top-4" aria-label="Sơ đồ đề">
      <dl className="grid grid-cols-3 rounded-sm border border-line bg-surface text-center">
        {(
          [
            ["Ô xong", counts.done],
            ["Đang sinh", counts.run],
            ["Chờ", counts.wait],
          ] as const
        ).map(([k, v]) => (
          <div key={k} className="border-r border-line px-1 py-2 last:border-r-0">
            <dd className="text-lg font-semibold tabular-nums">{v}</dd>
            <dt className="text-[11px] text-muted">{k}</dt>
          </div>
        ))}
      </dl>
      {PARTS.map(({ part, type }) => {
        let no = 0;
        const slots = rows
          .filter((r) => r.cell.type === type)
          .flatMap((r) =>
            Array.from({ length: r.cell.count }, (_, k) => ({ cellId: r.cell.id, no: ++no, state: k < r.done ? "done" : r.view })),
          );
        if (slots.length === 0) return null;
        return (
          <div key={part}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Phần {part} · {TYPE_LABEL[type]}
            </h3>
            <div className="grid grid-cols-6 gap-1.5">
              {slots.map((s) => (
                <button
                  key={s.no}
                  type="button"
                  title={`Câu ${s.no} phần ${part}`}
                  aria-label={`Câu ${s.no} phần ${part}`}
                  onClick={() => onPick(s.cellId)}
                  className={cn(
                    "aspect-square cursor-pointer rounded-sm border text-xs font-medium tabular-nums",
                    s.state === "done" && "border-ok bg-ok text-surface",
                    s.state === "run" && "animate-pulse border-accent bg-accent/15 text-accent",
                    s.state === "wait" && "border-line bg-surface text-muted",
                    hl === s.cellId && "outline-2 outline-offset-1 outline-ink",
                  )}
                >
                  {s.no}
                </button>
              ))}
            </div>
          </div>
        );
      })}
      <p className="text-xs text-muted">Mỗi ô vuông là một câu trong đề. Bấm để tìm ô ma trận tạo ra câu đó.</p>
    </aside>
  );
}

function CellList({
  rows,
  hl,
  busy,
  onRetry,
}: Readonly<{ rows: ViewRow[]; hl: string | null; busy: boolean; onRetry: (cellId: string) => void }>) {
  // Flat list in matrix order (sort_order), same numbering as the matrix check page.
  return (
    <div className="min-w-0">
      {rows.map((r) => {
        const [label, tone] = STATE_CHIP[r.view];
        const pct = r.view === "run" ? 100 : (r.done / Math.max(1, r.cell.count)) * 100;
        return (
          <div
            key={r.cell.id}
            id={`cell-${r.cell.id}`}
            className={cn(
              "grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-x-4 gap-y-2 rounded-sm border-b border-line px-1.5 py-3 text-sm sm:grid-cols-[minmax(0,1.3fr)_minmax(5rem,1fr)_3rem_11rem]",
              hl === r.cell.id && "bg-accent/10",
            )}
          >
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-xs tabular-nums text-muted">Ô {r.cell.sort_order}</span>
              <span className="basis-full text-xs text-muted">
                {r.cell.topic} · {r.cell.content_unit || "Cả chủ đề"}
              </span>
              <Chip>{TYPE_LABEL[r.cell.type]}</Chip>
              <span>
                {r.cell.type === "true_false" && r.cell.statement_levels
                  ? r.cell.statement_levels.map((l, k) => `${"abcd"[k]}) ${l}`).join(" · ")
                  : r.cell.level}
              </span>
            </span>
            <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-soft sm:col-span-1" aria-hidden="true">
              <div
                className={cn("h-full", r.view === "done" && "bg-ok", r.view === "run" && "animate-pulse bg-accent/50", r.view === "wait" && "bg-ok/60")}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="row-start-1 text-right tabular-nums text-muted sm:row-auto">
              {r.view === "done" || r.done > 0 ? `${r.done}/${r.cell.count}` : `–/${r.cell.count}`}
            </span>
            <span className="col-span-2 flex items-center gap-2 sm:col-span-1 sm:justify-end">
              <Chip tone={tone}>{label}</Chip>
              {r.manual && (
                <Button variant="outline" className="h-8" disabled={busy} onClick={() => onRetry(r.cell.id)}>
                  Sinh lại
                </Button>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
