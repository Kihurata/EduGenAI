import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "@/api";
import { formatTime, useAction, usePolling } from "@/common";
import { Chip } from "@/components/Chip";
import { Stepper } from "@/components/Stepper";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { LEVELS, QUESTION_TYPES, TYPE_LABEL, type Accepted, type CellIn, type Level, type Matrix, type QuestionType } from "@/types";

import { useSubjects } from "@/subjects";

import { examTitleFromMatrix, FormError, StatusChip, taClass, teacherSteps } from "./lib";

const LV_SHORT: Record<Level, string> = { "Biết": "B", "Hiểu": "H", "Vận dụng": "VD" };
const PART_COLS: { type: QuestionType; part: string; note: string }[] = [
  { type: "multiple_choice", part: "Phần I", note: "Nhiều lựa chọn" },
  { type: "true_false", part: "Phần II", note: "Đúng/Sai · số ý" },
  { type: "short_answer", part: "Phần III", note: "Trả lời ngắn" },
];
const WHOLE_TOPIC = "Cả chủ đề";

function toInput(m: Matrix): CellIn[] {
  return m.cells.map(({ topic, content_unit, type, level, count, statement_levels, statement_units, competency_codes }) => ({
    topic,
    content_unit,
    type,
    level,
    count,
    statement_levels,
    statement_units: statement_units ?? null,
    competency_codes,
  }));
}

function maxLevel(levels: Level[]): Level {
  return LEVELS[Math.max(...levels.map((l) => LEVELS.indexOf(l)))];
}

const tfLevels = (c: CellIn): Level[] => c.statement_levels ?? (Array<Level>(4).fill(c.level));

/** A whole cell (k = null) or one Đúng/Sai statement k (0–3 = a–d) of cell i, placed in one matrix row. */
interface Entry {
  i: number;
  k: number | null;
}
interface Row {
  unit: string | null;
  entries: Entry[];
}
interface TopicGroup {
  topic: string;
  rows: Row[];
}

const unitOf = (c: CellIn, k: number | null): string | null =>
  ((k !== null ? c.statement_units?.[k] : null) ?? c.content_unit)?.trim() || null;

/** Distinct cell indices of the given entries, in order. */
const cellsOf = (entries: Entry[]): number[] => [...new Set(entries.map((e) => e.i))];

/**
 * Groups cells like the paper matrix: topic → content unit (null = whole topic, listed last).
 * A Đúng/Sai question whose statements belong to different units is split: each statement sits in its own unit's row.
 */
function groupCells(cells: CellIn[]): TopicGroup[] {
  const groups: TopicGroup[] = [];
  const place = (topic: string, unit: string | null, entry: Entry) => {
    let g = groups.find((x) => x.topic === topic);
    if (!g) groups.push((g = { topic, rows: [] }));
    let r = g.rows.find((x) => x.unit === unit);
    if (!r) g.rows.push((r = { unit, entries: [] }));
    r.entries.push(entry);
  };
  cells.forEach((c, i) => {
    const topic = c.topic.trim() || "(Chưa có chủ đề)";
    if (c.type === "true_false" && c.statement_units) [0, 1, 2, 3].forEach((k) => place(topic, unitOf(c, k), { i, k }));
    else place(topic, unitOf(c, null), { i, k: null });
  });
  for (const g of groups) g.rows.sort((a, b) => Number(a.unit === null) - Number(b.unit === null));
  return groups;
}

/** Does this entry count under (type, level)? Đúng/Sai entries count statements, the others count questions. */
function matches(c: CellIn, k: number | null, type: QuestionType, level: Level): boolean {
  if (c.type !== type) return false;
  if (type !== "true_false") return c.level === level;
  return k === null ? tfLevels(c).includes(level) : tfLevels(c)[k] === level;
}

/** Questions (or, for Đúng/Sai, statements) of one type and level among the given entries. */
function amount(cells: CellIn[], entries: Entry[], type: QuestionType, level: Level): number {
  return entries.reduce((s, { i, k }) => {
    const c = cells[i];
    if (!matches(c, k, type, level)) return s;
    if (type !== "true_false") return s + c.count;
    return s + (k === null ? tfLevels(c).filter((l) => l === level).length : 1) * c.count;
  }, 0);
}

/** Asked items of a row, as on the paper's "Tổng số lệnh hỏi": questions, and statements for Đúng/Sai. */
function itemsOf(cells: CellIn[], entries: Entry[]): number {
  return entries.reduce((s, { i, k }) => {
    const c = cells[i];
    if (c.type !== "true_false") return s + c.count;
    return s + (k === null ? 4 : 1) * c.count;
  }, 0);
}

interface Drawer {
  title: string;
  sub: string;
  idx: number[];
  /** Index of a cell just added by clicking an empty grid cell: the drawer offers "Hoàn tác". */
  added?: number;
}

/** Số câu / số phút là số nguyên: chặn ký tự thập phân, dấu và số mũ ngay khi gõ. */
function blockNonInteger(e: ReactKeyboardEvent<HTMLInputElement>) {
  if ([".", ",", "e", "E", "+", "-"].includes(e.key)) e.preventDefault();
}

/** Chữ trong ô số → số nguyên 0..max (0 = ô đang trống; dán "1.9" thành 1). */
function wholeNumber(text: string, max: number): number {
  const n = Math.trunc(Number(text.replace(",", ".")));
  return Number.isFinite(n) ? Math.min(Math.max(n, 0), max) : 0;
}

/** Lớp sinh được đề (khớp SUPPORTED_GRADES ở BE): 10–11 kiểm tra định kỳ, 12 tốt nghiệp THPT. */
const SUPPORTED_GRADES = [10, 11, 12];

function gradeMessage(grade: number | null) {
  return grade
    ? `Hệ thống chỉ hỗ trợ đề lớp 10, 11, 12. Ma trận này là lớp ${grade} nên chưa sinh đề được.`
    : "Chưa xác định được lớp của ma trận. Chọn lớp (10, 11 hoặc 12) rồi bấm “Xác nhận & sinh đề”.";
}

export default function MatrixCheckPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const [cells, setCells] = useState<CellIn[]>([]);
  const [name, setName] = useState("");
  const [grade, setGrade] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [title, setTitle] = useState<string | null>(null);
  const subjects = useSubjects();
  const [duration, setDuration] = useState(90);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [drawer, setDrawer] = useState<Drawer | null>(null);
  const loader = useAction();
  const action = useAction();

  const apply = useCallback((m: Matrix) => {
    setMatrix(m);
    setCells(toInput(m));
    setName(m.name ?? "");
    setGrade(m.grade);
    setDirty(false);
  }, []);

  const load = useCallback(() => {
    // API: GET /api/v1/matrices/{id}
    void loader.run(async () => apply(await api<Matrix>(`/matrices/${id}`)));
  }, [id, apply]);
  useEffect(load, [load]);
  const converting = matrix?.status === "uploaded" || matrix?.status === "converting";
  usePolling(load, converting);

  const head = (
    <>
      <Stepper steps={teacherSteps({ matrix: id })} current={1} />
      <p className="text-xs uppercase tracking-wider text-muted">Bước 2 trên 5 · Kiểm tra ma trận</p>
      <h1 className="mb-1 text-2xl font-semibold">{matrix?.name || name || "Kiểm tra ma trận"}</h1>
    </>
  );

  // Cấu trúc đề theo môn của ma trận (GET /subjects, T-064): Toán 12/4/6, Lý/Hóa 18/4/6.
  const subject = subjects?.find((s) => s.code === matrix?.subject) ?? null;
  const subjectDuration = subject?.duration_minutes;
  useEffect(() => {
    if (subjectDuration) setDuration(subjectDuration);
  }, [subjectDuration]);

  if (!matrix) {
    return (
      <section>
        {head}
        {loader.error ? <ErrorState message="Không tải được ma trận." onRetry={load} /> : <p className="py-6 text-sm text-muted">Đang tải…</p>}
      </section>
    );
  }

  const editable = matrix.status === "parsed" || matrix.status === "invalid";
  const totals = QUESTION_TYPES.map((t) => ({
    type: t,
    count: cells.filter((c) => c.type === t).reduce((s, c) => s + c.count, 0),
  }));
  const total = totals.reduce((s, t) => s + t.count, 0);
  const official = subject?.question_counts;
  const expected = (t: QuestionType) => official?.[t] ?? "?";
  const expectedTotal = official ? QUESTION_TYPES.reduce((s, t) => s + official[t], 0) : "?";
  const points = totals.reduce((s, t) => s + t.count * (subject?.points[t.type] ?? 0), 0);
  const structureOk = !!official && totals.every((t) => t.count === official[t.type]);
  let confirmHint = "";
  const emptyCells = cells.flatMap((c, i) => (c.count < 1 ? [i] : []));
  const gradeOk = grade !== null && SUPPORTED_GRADES.includes(grade); // lớp đang chọn: bấm “Xác nhận & sinh đề” sẽ lưu lớp này trước
  if (!gradeOk) confirmHint = gradeMessage(grade);
  else if (!dirty && matrix.status === "invalid") confirmHint = "Sửa hết lỗi trước";
  else if (emptyCells.length) confirmHint = `Ô ${emptyCells.map((i) => i + 1).join(", ")} chưa có số câu (cần ít nhất 1)`;
  else if (duration < 1) confirmHint = "Nhập thời gian làm bài (phút)";
  else if (!official) confirmHint = "Chưa xác định được môn của ma trận";
  else if (!structureOk)
    confirmHint = `Cấu trúc phải là ${official.multiple_choice} nhiều lựa chọn / ${official.true_false} đúng-sai / ${official.short_answer} trả lời ngắn`;

  const groups = groupCells(cells);
  const unitCount = groups.reduce((s, g) => s + g.rows.length, 0);

  function edit(i: number, patch: Partial<CellIn>) {
    setCells((prev) => prev.map((c, j) => (j === i ? { ...c, ...patch } : c)));
    setDirty(true);
  }

  function setType(i: number, type: QuestionType) {
    const tf = type === "true_false";
    const statement_levels = tf ? (cells[i].statement_levels ?? new Array(4).fill(cells[i].level)) : null;
    edit(i, { type, statement_levels, statement_units: tf ? cells[i].statement_units : null });
  }

  function setStatementLevel(i: number, k: number, level: Level) {
    const levels = [...tfLevels(cells[i])];
    levels[k] = level;
    edit(i, { statement_levels: levels, level: maxLevel(levels) });
  }

  function setStatementUnit(i: number, k: number, unit: string | null) {
    const units = [0, 1, 2, 3].map((j) => unitOf(cells[i], j));
    units[k] = unit;
    edit(i, { statement_units: units });
  }

  /** Content units already used under a topic, offered when moving a statement to another row. */
  const unitsOfTopic = (topic: string): string[] =>
    groups.find((g) => g.topic === (topic.trim() || "(Chưa có chủ đề)"))?.rows.flatMap((r) => (r.unit ? [r.unit] : [])) ?? [];

  function removeCell(i: number) {
    setCells((prev) => prev.filter((_, j) => j !== i));
    setDirty(true);
    setDrawer((d) => (d ? { ...d, idx: d.idx.filter((j) => j !== i).map((j) => (j > i ? j - 1 : j)) } : d));
  }

  function addCell(base?: Partial<CellIn>) {
    const cell: CellIn = {
      topic: base?.topic ?? groups[0]?.topic ?? "",
      content_unit: base?.content_unit ?? null,
      type: base?.type ?? "multiple_choice",
      level: base?.level ?? "Biết",
      count: 1,
      statement_levels: base?.type === "true_false" ? new Array<Level>(4).fill(base.level ?? "Biết") : null,
      statement_units: null,
      competency_codes: [],
    };
    const index = cells.length;
    setCells((prev) => [...prev, cell]);
    setDirty(true);
    setDrawer((d) => (d ? { ...d, idx: [...d.idx, index] } : { title: "Ô mới", sub: "Thêm ô ma trận", idx: [index], added: index }));
  }

  function openCells(f: { row: Row; type?: QuestionType; level?: Level }, label: string, sub: string) {
    const entries = f.type ? f.row.entries.filter(({ i, k }) => matches(cells[i], k, f.type!, f.level!)) : f.row.entries;
    setDrawer({ title: label, sub, idx: cellsOf(entries) });
  }

  const examTitle = title ?? examTitleFromMatrix(matrix.name);

  /**
   * One button for the whole step: saves pending edits (if any), confirms the matrix, then starts
   * generating. Stops after saving when the saved matrix still has issues (they are shown above).
   */
  async function confirmAndGenerate(e: FormEvent) {
    e.preventDefault();
    const accepted = await action.run(async () => {
      let m: Matrix = matrix!;
      if (editable) {
        if (dirty) {
          // API: PUT /api/v1/matrices/{id}/cells
          m = await api<Matrix>(`/matrices/${id}/cells`, {
            method: "PUT",
            json: { cells, name: name || null, grade },
          });
          apply(m);
        }
        if (m.status !== "parsed") return undefined;
        // API: POST /api/v1/matrices/{id}/confirm
        m = await api<Matrix>(`/matrices/${id}/confirm`, { method: "POST" });
        apply(m);
      }
      // API: POST /api/v1/exams
      return api<Accepted>("/exams", { method: "POST", json: { matrix_id: id, duration_minutes: duration, title: examTitle.trim() || null } });
    });
    if (accepted) navigate(`/exams?exam=${accepted.id}`);
  }

  // Column sums of the grid footer.
  const allEntries: Entry[] = cells.map((_, i) => ({ i, k: null }));
  const colSum = (type: QuestionType, level: Level) => amount(cells, allEntries, type, level);

  return (
    <section>
      {head}
      <p className="mb-5 flex flex-wrap items-center gap-2 text-sm text-muted">
        <StatusChip status={matrix.status} />
        <span className="break-all">{matrix.source_filename}</span> · tải lên {formatTime(matrix.created_at)}
        {matrix.confirmed_at && <> · xác nhận {formatTime(matrix.confirmed_at)}</>}
      </p>

      {converting && <p className="mb-4 text-sm text-muted">Đang đọc ảnh ma trận, có thể mất vài phút…</p>}
      {matrix.error_message && (
        <p role="alert" className="mb-4 text-sm text-bad">
          {matrix.error_message}
        </p>
      )}
      {!gradeOk && cells.length > 0 && (
        <p role="alert" className="mb-4 border-l-2 border-bad pl-4 text-sm text-bad">
          {gradeMessage(grade)}
        </p>
      )}
      {matrix.issues.length > 0 && (
        <div className="mb-6 border-l-2 border-warn pl-4 text-sm">
          <p className="font-medium text-warn">Ma trận còn lỗi, sửa rồi bấm “Xác nhận & sinh đề” lại</p>
          <ul className="mt-1 list-disc pl-5">
            {matrix.issues.map((issue, i) => (
              <li key={i}>
                {issue.location && <code className="text-muted">{issue.location}</code>} {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {cells.length > 0 && (
        <>
          <div className="mb-5 grid gap-4 sm:grid-cols-[minmax(0,1fr)_8rem_8rem]">
            <label className="text-sm">
              <span className="mb-1 block text-muted">Tên ma trận</span>
              <Input
                value={name}
                disabled={!editable}
                onChange={(e) => {
                  setName(e.target.value);
                  setDirty(true);
                }}
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted">Môn</span>
              <Input value={subject?.label ?? matrix.subject ?? "Chưa rõ"} readOnly disabled />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted">Lớp</span>
              <Select
                value={grade ?? ""}
                disabled={!editable}
                onChange={(e) => {
                  setGrade(e.target.value ? Number(e.target.value) : null);
                  setDirty(true);
                }}
              >
                {matrix.grade === null && <option value="">Chưa rõ</option>}
                {SUPPORTED_GRADES.map((g) => (
                  <option key={g} value={g}>
                    Lớp {g}
                  </option>
                ))}
              </Select>
            </label>
          </div>

          <p className="mb-4 rounded-sm border border-line bg-surface px-4 py-2.5 text-sm">
            Đã đọc <b>{cells.length} ô</b> từ <b>{groups.length} chủ đề</b>, <b>{unitCount} dòng nội dung</b>. Bảng dưới giữ bố cục ma trận gốc.{" "}
            {editable ? "Bấm vào một con số để sửa các ô tạo ra nó, hoặc bấm tên nội dung để sửa cả dòng." : "Bấm vào một con số hoặc tên nội dung để xem chi tiết các ô."}
          </p>

          <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex gap-0.5 rounded-sm border border-line bg-surface p-0.5" role="group" aria-label="Kiểu hiển thị">
              {(
                [
                  ["grid", "Bảng ma trận"],
                  ["list", "Danh sách ô"],
                ] as const
              ).map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className={cn("cursor-pointer rounded-sm px-3 py-1 text-sm font-medium", view === v ? "bg-accent text-surface" : "text-muted hover:text-ink")}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
              <span>B = Biết · H = Hiểu · VD = Vận dụng</span>
              <span>Phần II đếm theo số ý</span>
              {editable && (
                <Button variant="outline" className="h-8" onClick={() => addCell()}>
                  + Thêm ô
                </Button>
              )}
            </div>
          </div>

          <div className="overflow-x-auto">
            {view === "grid" ? (
              <table className="w-full min-w-[54rem] border-collapse bg-surface text-sm">
                <thead className="bg-soft text-xs">
                  <tr>
                    <th rowSpan={2} className="border border-line px-3 py-2 text-left font-medium">
                      Nội dung kiến thức
                    </th>
                    {PART_COLS.map((p) => (
                      <th key={p.type} colSpan={3} className="border border-line px-2 py-1.5 font-semibold">
                        {p.part}
                        <span className="block font-normal text-muted">{p.note}</span>
                      </th>
                    ))}
                    <th rowSpan={2} className="border border-line px-2 py-2 font-medium">
                      Tổng
                      <br />
                      lệnh hỏi
                    </th>
                  </tr>
                  <tr>
                    {PART_COLS.flatMap((p) =>
                      LEVELS.map((l) => (
                        <th key={p.type + l} className="w-[6%] border border-line px-1 py-1.5 font-medium">
                          {LV_SHORT[l]}
                        </th>
                      )),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {groups.map((g, gi) => (
                    <GroupRows
                      key={g.topic}
                      group={g}
                      gi={gi}
                      cells={cells}
                      onOpen={openCells}
                      onAdd={editable ? (row, type, level) => addCell({ topic: g.topic, content_unit: row.unit, type, level }) : undefined}
                    />
                  ))}
                </tbody>
                <tfoot className="tabular-nums">
                  <tr className="bg-soft font-semibold">
                    <td className="border border-line px-3 py-2">Tổng theo mức độ</td>
                    {PART_COLS.flatMap((p) =>
                      LEVELS.map((l) => (
                        <td key={p.type + l} className="border border-line px-1 py-2 text-center">
                          {colSum(p.type, l)}
                          {p.type === "true_false" && <span className="font-normal text-muted"> ý</span>}
                        </td>
                      )),
                    )}
                    <td className="border border-line px-1 py-2 text-center">{itemsOf(cells, allEntries)}</td>
                  </tr>
                  <tr>
                    <td className="border border-line px-3 py-2 font-medium">Số câu theo phần</td>
                    {totals.map((t) => {
                      const ok = t.count === official?.[t.type];
                      return (
                        <td key={t.type} colSpan={3} className="border border-line px-1 py-2 text-center">
                          <Chip tone={ok ? "ok" : "bad"}>
                            {t.count} / {expected(t.type)} câu {ok && "✓"}
                          </Chip>
                        </td>
                      );
                    })}
                    <td className="border border-line" />
                  </tr>
                </tfoot>
              </table>
            ) : (
              <table className="w-full min-w-[46rem] border-collapse bg-surface text-sm">
                <thead className="bg-soft text-left text-xs text-muted">
                  <tr>
                    <th className="w-12 border-b border-line px-3 py-2 font-medium">Ô</th>
                    <th className="border-b border-line px-3 py-2 font-medium">Chủ đề / nội dung</th>
                    <th className="w-36 border-b border-line px-3 py-2 font-medium">Dạng</th>
                    <th className="w-40 border-b border-line px-3 py-2 font-medium">Mức độ</th>
                    <th className="w-16 border-b border-line px-3 py-2 font-medium">Số câu</th>
                    <th className="w-16 border-b border-line px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {cells.map((c, i) => (
                    <tr key={i} className="align-top">
                      <td className="border-b border-line px-3 py-3 tabular-nums text-muted">{i + 1}</td>
                      <td className="border-b border-line px-3 py-3">
                        <div className="text-xs text-muted">{c.topic || "(Chưa có chủ đề)"}</div>
                        <div className="leading-snug">{c.content_unit || <span className="text-muted">{WHOLE_TOPIC}</span>}</div>
                        {c.type === "true_false" && c.statement_units && !c.content_unit && (
                          <ul className="mt-1 text-xs text-muted">
                            {[0, 1, 2, 3].map((k) => (
                              <li key={k}>
                                {"abcd"[k]}) {unitOf(c, k) ?? WHOLE_TOPIC}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td className="border-b border-line px-3 py-3">
                        <Chip>{TYPE_LABEL[c.type]}</Chip>
                      </td>
                      <td className="border-b border-line px-3 py-3">
                        {c.type === "true_false" ? (
                          <div className="grid grid-cols-2 gap-x-3 text-xs">
                            {tfLevels(c).map((l, k) => (
                              <span key={k}>
                                <span className="text-muted">{"abcd"[k]})</span> {l}
                              </span>
                            ))}
                          </div>
                        ) : (
                          c.level
                        )}
                      </td>
                      <td className={cn("border-b border-line px-3 py-3 font-semibold tabular-nums", c.count < 1 && "text-bad")}>{c.count || "Trống"}</td>
                      <td className="border-b border-line px-3 py-3">
                        <button type="button" className="cursor-pointer text-accent hover:underline" onClick={() => setDrawer({ title: `Ô ${i + 1}`, sub: editable ? "Sửa ô ma trận" : "Chi tiết ô", idx: [i] })}>
                          {editable ? "Sửa" : "Xem"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      <FormError error={action.error} />

      <div className="sticky bottom-0 z-10 mt-6 rounded-sm border border-line bg-surface">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 text-sm">
          <div className="flex flex-wrap items-center gap-5">
            <Stat label="Tổng" value={`${total}/${expectedTotal} câu · ${points} điểm`} ok={structureOk} />
            {totals.map((t, k) => (
              <Stat key={t.type} label={`Phần ${["I", "II", "III"][k]}`} value={`${t.count}/${expected(t.type)}`} ok={t.count === official?.[t.type]} />
            ))}
          </div>
          <div className="ml-auto flex flex-wrap items-end gap-2">
            {(editable || matrix.status === "confirmed") && (
              <form onSubmit={confirmAndGenerate} className="flex flex-wrap items-end gap-2">
                {editable && confirmHint && (
                  <span className="basis-full text-right text-xs text-warn">
                    {confirmHint}
                    {emptyCells.length > 0 && (
                      <button
                        type="button"
                        className="ml-2 cursor-pointer font-medium text-accent underline"
                        onClick={() => setDrawer({ title: "Ô chưa có số câu", sub: "Cần sửa", idx: emptyCells })}
                      >
                        Sửa các ô này
                      </button>
                    )}
                  </span>
                )}
                {editable && !confirmHint && (
                  <span className="basis-full text-right text-xs text-muted">
                    Bấm nút sẽ lưu và chốt ma trận (sau đó không sửa được nữa), rồi bắt đầu sinh đề.
                  </span>
                )}
                <label className="text-xs">
                  <span className="mb-1 block text-muted">Tên đề thi</span>
                  <Input className="w-64 max-w-full" value={examTitle} placeholder="Ví dụ: Đề kiểm tra giữa kì 1 – Toán 12" onChange={(e) => setTitle(e.target.value)} />
                </label>
                <label className="text-xs">
                  <span className="mb-1 block text-muted">Thời gian (phút, tối đa 300)</span>
                  <Input
                    type="number"
                    inputMode="numeric"
                    step={1}
                    className={cn("w-24", duration < 1 && "border-bad")}
                    min={1}
                    max={300}
                    aria-invalid={duration < 1}
                    value={duration || ""}
                    onKeyDown={blockNonInteger}
                    onChange={(e) => setDuration(wholeNumber(e.target.value, 300))}
                  />
                </label>
                <Button type="submit" disabled={(editable && !!confirmHint) || action.busy} title={editable ? confirmHint : undefined}>
                  {action.busy ? "Đang xử lý…" : editable ? "Xác nhận & sinh đề" : "Sinh đề"}
                </Button>
              </form>
            )}
            {!editable && matrix.status !== "confirmed" && (
              <span className="text-muted">{converting ? "Đang chờ đọc xong…" : "Không thể sinh đề từ ma trận này"}</span>
            )}
          </div>
        </div>
      </div>

      {drawer && (
        <CellDrawer
          drawer={drawer}
          cells={cells}
          editable={editable}
          onClose={() => setDrawer(null)}
          onEdit={edit}
          onType={setType}
          onStatementLevel={setStatementLevel}
          onStatementUnit={setStatementUnit}
          unitsOf={unitsOfTopic}
          onRemove={removeCell}
          onAdd={() => addCell(drawer.idx.length ? { topic: cells[drawer.idx[0]].topic, content_unit: cells[drawer.idx[0]].content_unit } : undefined)}
          onUndoAdd={() => {
            if (drawer.added !== undefined) removeCell(drawer.added);
            setDrawer(null);
          }}
        />
      )}
    </section>
  );
}

function Stat({ label, value, ok }: Readonly<{ label: string; value: string; ok: boolean }>) {
  return (
    <div className="grid leading-tight">
      <span className="text-xs text-muted">{label}</span>
      <span className={cn("font-semibold tabular-nums", ok ? "text-ok" : "text-bad")}>{value}</span>
    </div>
  );
}

function GroupRows({
  group,
  gi,
  cells,
  onOpen,
  onAdd,
}: Readonly<{
  group: TopicGroup;
  gi: number;
  cells: CellIn[];
  onOpen: (f: { row: Row; type?: QuestionType; level?: Level }, label: string, sub: string) => void;
  /** Editable matrix only: an empty grid cell adds a new matrix cell at that row / type / level. */
  onAdd?: (row: Row, type: QuestionType, level: Level) => void;
}>) {
  return (
    <>
      <tr>
        <td colSpan={11} className="border border-line bg-paper/60 px-3 py-2 font-semibold">
          Chủ đề {gi + 1}. {group.topic} <span className="font-normal text-muted">· {cellsOf(group.rows.flatMap((r) => r.entries)).length} ô</span>
        </td>
      </tr>
      {group.rows.map((row, ri) => {
        const unitLabel = row.unit ?? WHOLE_TOPIC;
        return (
          <tr key={unitLabel}>
            <td className="w-[34%] border border-line px-3 py-2.5">
              <button type="button" className="cursor-pointer text-left leading-snug hover:text-accent hover:underline" onClick={() => onOpen({ row }, unitLabel, `Cả dòng · ${group.topic}`)}>
                <span className="mr-1.5 tabular-nums text-muted">
                  {gi + 1}.{ri + 1}
                </span>
                {unitLabel}
              </button>
            </td>
            {PART_COLS.flatMap((p) =>
              LEVELS.map((l) => {
                const v = amount(cells, row.entries, p.type, l);
                const hasEmpty = row.entries.some(({ i, k }) => matches(cells[i], k, p.type, l) && cells[i].count < 1);
                return (
                  // The button fills the whole grid cell, so a click anywhere in it opens (or adds) the cell.
                  <td key={p.type + l} className="h-px border border-line p-0 text-center">
                    {v || hasEmpty ? (
                      <button
                        type="button"
                        aria-label={`${unitLabel}: ${TYPE_LABEL[p.type]}, ${l}, ${hasEmpty ? "có ô chưa có số câu" : `${v} ${p.type === "true_false" ? "ý" : "câu"}`}`}
                        onClick={() => onOpen({ row, type: p.type, level: l }, `${TYPE_LABEL[p.type]} · ${l}`, unitLabel)}
                        className={cn(
                          "h-full min-h-10 w-full cursor-pointer px-2 py-1 font-semibold tabular-nums hover:bg-accent/10 hover:text-accent focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent",
                          hasEmpty && "bg-bad/10 text-bad outline outline-1 -outline-offset-1 outline-bad",
                        )}
                      >
                        {hasEmpty && !v ? "?" : v}
                        {p.type === "true_false" && <span className="text-xs font-normal text-muted"> ý</span>}
                      </button>
                    ) : onAdd ? (
                      <button
                        type="button"
                        title="Thêm ô ma trận vào đây"
                        aria-label={`Thêm ô: ${unitLabel}, ${TYPE_LABEL[p.type]}, ${l}`}
                        onClick={() => onAdd(row, p.type, l)}
                        className="group h-full min-h-10 w-full cursor-pointer text-muted/60 hover:bg-accent/5 hover:text-accent focus-visible:bg-accent/5 focus-visible:text-accent focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
                      >
                        <span className="group-hover:hidden group-focus-visible:hidden">·</span>
                        <span className="hidden text-sm group-hover:inline group-focus-visible:inline">+</span>
                      </button>
                    ) : (
                      <span className="text-line">·</span>
                    )}
                  </td>
                );
              }),
            )}
            <td className="border border-line bg-paper/40 px-1 text-center font-semibold tabular-nums">
              {itemsOf(cells, row.entries)}
            </td>
          </tr>
        );
      })}
    </>
  );
}

interface DrawerProps {
  drawer: Drawer;
  cells: CellIn[];
  editable: boolean;
  onClose: () => void;
  onEdit: (i: number, patch: Partial<CellIn>) => void;
  onType: (i: number, t: QuestionType) => void;
  onStatementLevel: (i: number, k: number, l: Level) => void;
  onStatementUnit: (i: number, k: number, unit: string | null) => void;
  /** Content units already in the matrix under a topic. */
  unitsOf: (topic: string) => string[];
  onRemove: (i: number) => void;
  onAdd: () => void;
  /** Removes the cell just added from the grid and closes the drawer. */
  onUndoAdd: () => void;
}

function CellDrawer({
  drawer,
  cells,
  editable,
  onClose,
  onEdit,
  onType,
  onStatementLevel,
  onStatementUnit,
  unitsOf,
  onRemove,
  onAdd,
  onUndoAdd,
}: Readonly<DrawerProps>) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close.current();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-ink/25" onClick={onClose} aria-hidden />
      <aside
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cell-drawer-title"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-line bg-surface outline-none"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-muted">
              {drawer.sub} · {drawer.idx.length} ô
            </p>
            <h2 id="cell-drawer-title" className="text-base font-semibold leading-snug">
              {drawer.title}
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {editable && drawer.added !== undefined && (
              <Button variant="outline" className="h-8" onClick={onUndoAdd}>
                Hoàn tác thêm ô
              </Button>
            )}
            <Button variant="ghost" aria-label="Đóng" onClick={onClose}>
              ✕
            </Button>
          </div>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {!editable && <p className="rounded-sm bg-soft px-3 py-2 text-sm text-muted">Ma trận đã xác nhận nên chỉ xem được, không sửa được.</p>}
          {drawer.idx.length === 0 && <p className="text-sm text-muted">Không còn ô nào ở đây.</p>}
          {drawer.idx.map((i) => {
            const c = cells[i];
            if (!c) return null;
            return (
              <div key={i} className="space-y-3 border-b border-line pb-5 text-sm last:border-b-0">
                <div className="flex items-center justify-between">
                  <strong>Ô {i + 1}</strong>
                  {editable && (
                    <Button variant="ghost" className="h-7 text-son" onClick={() => onRemove(i)}>
                      Xoá ô
                    </Button>
                  )}
                </div>
                <label className="block">
                  <span className="mb-1 block text-muted">Chủ đề</span>
                  <textarea className={taClass} rows={2} value={c.topic} disabled={!editable} onChange={(e) => onEdit(i, { topic: e.target.value })} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-muted">Nội dung</span>
                  <textarea
                    className={taClass}
                    rows={2}
                    value={c.content_unit ?? ""}
                    placeholder="Để trống nếu ô áp dụng cho cả chủ đề"
                    disabled={!editable}
                    onChange={(e) => onEdit(i, { content_unit: e.target.value || null })}
                  />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="mb-1 block text-muted">Dạng câu hỏi</span>
                    <Select value={c.type} disabled={!editable} onChange={(e) => onType(i, e.target.value as QuestionType)}>
                      {QUESTION_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {TYPE_LABEL[t]}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-muted">Số câu (1–50)</span>
                    <Input
                      className={cn(c.count < 1 && "border-bad")}
                      aria-invalid={c.count < 1}
                      type="number"
                      inputMode="numeric"
                      step={1}
                      min={1}
                      max={50}
                      value={c.count || ""}
                      disabled={!editable}
                      onKeyDown={blockNonInteger}
                      onChange={(e) => onEdit(i, { count: wholeNumber(e.target.value, 50) })}
                    />
                  </label>
                </div>
                {c.type === "true_false" ? (
                  <fieldset>
                    <legend className="mb-1 text-muted">Mức độ từng ý</legend>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {tfLevels(c).map((lv, k) => (
                        <label key={k} className="block text-xs">
                          <span className="mb-1 block text-muted">Ý {"abcd"[k]})</span>
                          <Select value={lv} disabled={!editable} onChange={(e) => onStatementLevel(i, k, e.target.value as Level)}>
                            {LEVELS.map((l) => (
                              <option key={l}>{l}</option>
                            ))}
                          </Select>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                ) : null}
                {c.type === "true_false" ? (
                  <fieldset>
                    <legend className="mb-1 text-muted">Nội dung từng ý</legend>
                    <div className="space-y-2">
                      {[0, 1, 2, 3].map((k) => {
                        const unit = unitOf(c, k);
                        const options = [...new Set([...unitsOf(c.topic), ...(unit ? [unit] : [])])];
                        return (
                          <label key={k} className="flex items-center gap-2 text-xs">
                            <span className="w-8 shrink-0 text-muted">{"abcd"[k]})</span>
                            <Select value={unit ?? ""} disabled={!editable} onChange={(e) => onStatementUnit(i, k, e.target.value || null)}>
                              <option value="">{WHOLE_TOPIC}</option>
                              {options.map((u) => (
                                <option key={u} value={u}>
                                  {u}
                                </option>
                              ))}
                            </Select>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                ) : (
                  <label className="block">
                    <span className="mb-1 block text-muted">Mức độ</span>
                    <Select value={c.level} disabled={!editable} onChange={(e) => onEdit(i, { level: e.target.value as Level })}>
                      {LEVELS.map((l) => (
                        <option key={l}>{l}</option>
                      ))}
                    </Select>
                  </label>
                )}
                <label className="block">
                  <span className="mb-1 block text-muted">
                    Mã năng lực <span className="text-xs">(không bắt buộc, cách nhau bởi dấu phẩy)</span>
                  </span>
                  <Input
                    value={c.competency_codes.join(", ")}
                    disabled={!editable}
                    onChange={(e) =>
                      onEdit(i, {
                        competency_codes: e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
              </div>
            );
          })}
        </div>
        <footer className="flex items-center justify-between gap-2 border-t border-line px-5 py-3">
          {editable ? (
            <Button variant="ghost" onClick={onAdd}>
              + Thêm ô vào đây
            </Button>
          ) : (
            <span />
          )}
          <Button onClick={onClose}>Xong</Button>
        </footer>
      </aside>
    </>
  );
}
