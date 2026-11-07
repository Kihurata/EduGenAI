import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { api, download } from "@/api";
import { useAuth } from "@/auth";
import { keyed, MathText, QuestionStem, useAction } from "@/common";
import { Seal } from "@/components/Seal";
import { Stepper } from "@/components/Stepper";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { PART_OF_TYPE, type Exam, type Question } from "@/types";

import { FormError, LETTERS, mathOption, optionColumns, PAPER_FONT, PART_HEAD, PARTS, solutionSteps, teacherSteps } from "./lib";

// A4 at 96 dpi; the preview approximates the .docx layout (Times 12 pt), it is not a render of the file.
const SHEET_W = 794;
const SHEET_H = 1123;
const PAD_X = 56;
const PAD_TOP = 60;
const FOOTER = 76;
const BODY_H = SHEET_H - PAD_TOP - FOOTER;

type Variant = "student" | "teacher";
interface Block {
  kind: "head" | "part" | "q" | "end";
  node: ReactNode;
}

function PaperQuestion({ q, number, teacher }: Readonly<{ q: Question; number: number; teacher: boolean }>) {
  const c = q.content;
  const cols = c.options ? optionColumns(c.options, true) : 1;
  return (
    <div>
      <div>
        <b>Câu {number}.</b> <QuestionStem stem={c.stem} table={c.table} />
      </div>
      {c.type === "multiple_choice" && c.options && (
        <ol className={cn("grid gap-x-3", cols === 4 ? "grid-cols-4" : cols === 2 ? "grid-cols-2" : "grid-cols-1")}>
          {c.options.map((o, i) => (
            <li key={LETTERS[i]}>
              <b>{LETTERS[i]}.</b> <MathText text={mathOption(o)} />
            </li>
          ))}
        </ol>
      )}
      {c.type === "true_false" && c.statements && (
        <ol>
          {c.statements.map((s, i) => (
            <li key={"abcd"[i]} className="grid grid-cols-[1.5rem_minmax(0,1fr)] pl-1">
              <b>{"abcd"[i]})</b>
              <span>
                <MathText text={s.text} />
              </span>
            </li>
          ))}
        </ol>
      )}
      {teacher && (
        <div className="mt-1 border-l-2 border-[#999] pl-3 text-[15px]">
          <b>
            {c.type === "short_answer" ? "Đáp số" : "Đáp án"}:{" "}
            {c.type === "true_false" ? c.statements?.map((s, i) => `${"abcd"[i]}) ${s.correct ? "Đúng" : "Sai"}`).join("; ") : c.answer}
          </b>
          <ol className="list-decimal pl-5">
            {keyed(solutionSteps(c.solution ?? ""), "st").map(({ id, value: s }) => (
              <li key={id}>
                <MathText text={s} />
              </li>
            ))}
            {c.type === "true_false" &&
              c.statements?.map(
                (s, i) =>
                  s.explanation && (
                    <li key={`s-${"abcd"[i]}`}>
                      <b>{"abcd"[i]})</b> <MathText text={s.explanation} />
                    </li>
                  ),
              )}
          </ol>
        </div>
      )}
    </div>
  );
}

function KeyTable({ head, rows }: Readonly<{ head: (string | number)[]; rows: (string | number)[][] }>) {
  const cell = "border border-[#111] px-1 py-0.5";
  return (
    <table className="mt-1 w-full table-fixed border-collapse text-center text-[15px]">
      <tbody>
        <tr>
          {keyed(head, "h").map(({ id, value: h }) => (
            <th key={id} className={cell}>
              {h}
            </th>
          ))}
        </tr>
        {keyed(rows, "r").map(({ id, value: r }) => (
          <tr key={id}>
            {keyed(r, "c").map(({ id: cellId, value: v }) => (
              <td key={cellId} className={cell}>
                {v}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function buildBlocks(exam: Exam, teacher: boolean, school: string, pageCount: number): Block[] {
  const partOf = (q: Question) => q.part || PART_OF_TYPE[q.content.type];
  const sorted = [...exam.questions].sort((a, b) => a.position - b.position);
  const blocks: Block[] = [
    {
      kind: "head",
      node: (
        <>
          <table role="presentation" className="w-full text-center text-[15px]">
            <tbody>
              <tr className="align-top">
                <td className="w-1/2 px-1">
                  <div className="font-bold uppercase">{school || "TRƯỜNG ……………………"}</div>
                  <div className="mx-auto mt-0.5 w-24 border-b border-[#111]" />
                  <div className="mt-1.5 italic">
                    (Đề thi có {pageCount ? String(pageCount).padStart(2, "0") : "…"} trang)
                  </div>
                </td>
                <td className="w-1/2 px-1">
                  <div className="font-bold uppercase">{exam.title}</div>
                  <div className="font-bold">Môn: TOÁN – Lớp 12</div>
                  <div className="italic">Thời gian làm bài: {exam.duration_minutes} phút, không kể thời gian phát đề</div>
                </td>
              </tr>
            </tbody>
          </table>
          <div className="mt-4 flex items-center justify-between gap-4">
            <span>Họ, tên thí sinh: ………………………………… Số báo danh: …………</span>
            {teacher && <span className="border border-[#111] px-3 py-0.5 font-bold">Bản giáo viên</span>}
          </div>
        </>
      ),
    },
  ];
  for (const { part, type } of PARTS) {
    const qs = sorted.filter((q) => partOf(q) === part);
    if (qs.length === 0) continue;
    blocks.push({
      kind: "part",
      node: (
        <p className="mt-1.5 font-bold">
          {PART_HEAD[type][0]}{" "}
          <i className="font-normal">
            Thí sinh trả lời từ câu 1 đến câu {qs.length}. {PART_HEAD[type][1]}
          </i>
        </p>
      ),
    });
    qs.forEach((q, i) => blocks.push({ kind: "q", node: <PaperQuestion q={q} number={i + 1} teacher={teacher} /> }));
  }
  blocks.push({ kind: "end", node: <p className="mt-2 text-center font-bold">------ HẾT ------</p> });

  if (teacher) {
    const of = (t: string) => sorted.filter((q) => q.content.type === t);
    const mc = of("multiple_choice");
    const tf = of("true_false");
    const sa = of("short_answer");
    blocks.push({ kind: "part", node: <p className="mt-3 text-center font-bold">ĐÁP ÁN</p> });
    if (mc.length)
      blocks.push({
        kind: "q",
        node: (
          <div>
            <b>Phần I.</b> Mỗi câu trả lời đúng được 0,25 điểm.
            <KeyTable head={["Câu", ...mc.map((_, i) => i + 1)]} rows={[["Đáp án", ...mc.map((q) => q.content.answer)]]} />
          </div>
        ),
      });
    if (tf.length)
      blocks.push({
        kind: "q",
        node: (
          <div>
            <b>Phần II.</b> Đúng 1 ý: 0,1 đ · 2 ý: 0,25 đ · 3 ý: 0,5 đ · 4 ý: 1 đ.
            <KeyTable
              head={["Câu", ...tf.map((_, i) => i + 1)]}
              rows={[0, 1, 2, 3].map((k) => [`Ý ${"abcd"[k]})`, ...tf.map((q) => (q.content.statements?.[k] ? (q.content.statements[k].correct ? "Đ" : "S") : ""))])}
            />
          </div>
        ),
      });
    if (sa.length)
      blocks.push({
        kind: "q",
        node: (
          <div>
            <b>Phần III.</b> Mỗi câu trả lời đúng được 0,5 điểm.
            <KeyTable head={["Câu", ...sa.map((_, i) => i + 1)]} rows={[["Đáp số", ...sa.map((q) => q.content.answer)]]} />
          </div>
        ),
      });
  }
  return blocks;
}

/** Greedy pagination by measured block height; a part heading never ends a page. */
function paginate(blocks: Block[], heights: number[]): number[][] {
  const pages: number[][] = [[]];
  let used = 0;
  heights.forEach((h, i) => {
    const need = blocks[i].kind === "part" && i + 1 < heights.length ? h + heights[i + 1] : h;
    if (used + need > BODY_H && pages[pages.length - 1].length > 0) {
      pages.push([]);
      used = 0;
    }
    pages[pages.length - 1].push(i);
    used += h;
  });
  return pages;
}

export default function ExamExportPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [exam, setExam] = useState<Exam | null>(null);
  const [variant, setVariant] = useState<Variant>("student");
  const [zoom, setZoom] = useState("fit");
  const [fit, setFit] = useState(1);
  const [pages, setPages] = useState<number[][] | null>(null);
  const [fontsTick, setFontsTick] = useState(0);
  const measureRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const loader = useAction();
  const action = useAction();

  const load = useCallback(() => {
    // API: GET /api/v1/exams/{id}
    void loader.run(async () => setExam(await api<Exam>(`/exams/${id}`)));
  }, [id]);
  useEffect(load, [load]);

  useEffect(() => {
    void document.fonts?.ready.then(() => setFontsTick((t) => t + 1));
  }, []);

  const teacher = variant === "teacher";
  const pageCount = pages?.length ?? 0;
  const blocks = exam ? buildBlocks(exam, teacher, user?.school.name ?? "", pageCount) : [];

  // Measure the hidden copy of every block, then split into A4 pages.
  useLayoutEffect(() => {
    const root = measureRef.current;
    if (!exam || !root) return;
    const heights = [...root.children].map((el) => el.getBoundingClientRect().height);
    setPages(paginate(blocks, heights));
    // blocks are rebuilt every render; exam / variant / fonts are what change them
  }, [exam, variant, fontsTick]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setFit(Math.min(1, (el.clientWidth - 32) / (SHEET_W + 2))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [exam]);

  const head = (
    <>
      <Stepper steps={teacherSteps({ matrix: exam?.matrix_id, exam: id })} current={4} />
      <p className="text-xs uppercase tracking-wider text-muted">Bước 5 trên 5 · Xuất đề</p>
      <h1 className="text-2xl font-semibold">Xuất đề</h1>
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

  const approved = exam.status === "approved";
  // API: GET /api/v1/exams/{id}/export?variant=student|teacher (docx)
  const get = (v: Variant, name: string) => action.run(() => download(`/exams/${id}/export?variant=${v}`, name));
  const scale = zoom === "fit" ? fit : Number(zoom);
  const count = (t: string) => exam.questions.filter((q) => q.content.type === t).length;

  return (
    <section>
      {head}
      <p className="mt-1 mb-5 max-w-2xl text-muted">Bản xem trước dàn trang gần giống file Word sẽ tải về: khổ A4, Times New Roman 12 pt.</p>

      <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
            <div className="inline-flex gap-0.5 rounded-sm border border-line bg-surface p-0.5" role="group" aria-label="Phiên bản">
              {(
                [
                  ["student", "Bản học sinh"],
                  ["teacher", "Bản giáo viên"],
                ] as const
              ).map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={variant === v}
                  onClick={() => setVariant(v)}
                  className={cn("cursor-pointer rounded-sm px-3 py-1 font-medium", variant === v ? "bg-accent text-surface" : "text-muted hover:text-ink")}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="flex-1" />
            <label className="flex items-center gap-2 text-muted">
              Thu phóng
              <Select className="h-8 w-auto" value={zoom} onChange={(e) => setZoom(e.target.value)}>
                <option value="fit">Vừa khung</option>
                <option value="0.6">60%</option>
                <option value="0.8">80%</option>
                <option value="1">100%</option>
              </Select>
            </label>
            <span className="tabular-nums text-muted">{pageCount ? `${pageCount} trang A4` : ""}</span>
          </div>

          <div ref={scrollRef} className="max-h-[70rem] overflow-auto rounded-sm border border-line bg-soft p-4">
            <div className="grid justify-center gap-5" style={{ zoom: scale }}>
              {!pages && <p className="text-sm text-muted">Đang dàn trang…</p>}
              {pages && keyed(pages, "p").map(({ id: pageId, value: list }, pi) => (
                <div
                  key={pageId}
                  className={cn("relative overflow-hidden border border-line bg-white text-[16px] leading-normal text-[#111]", PAPER_FONT)}
                  style={{ width: SHEET_W, height: SHEET_H, padding: `${PAD_TOP}px ${PAD_X}px 0` }}
                >
                  {!approved && (
                    <div aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center">
                      <span className="-rotate-30 font-sans text-[110px] font-semibold tracking-widest text-son/10">BẢN NHÁP</span>
                    </div>
                  )}
                  {list.map((i) => (
                    <div key={i} className="pb-2">
                      {blocks[i]?.node}
                    </div>
                  ))}
                  <div className="absolute inset-x-14 bottom-7 flex justify-between border-t border-[#ccc] pt-1.5 text-[13px] text-[#555]">
                    <span>
                      Trang {pi + 1}/{pageCount}
                    </span>
                    <span>{teacher ? "Bản giáo viên" : "Bản học sinh"}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="space-y-4 text-sm lg:sticky lg:top-4">
          {approved ? (
            <div className="flex items-center gap-3">
              <span className="shrink-0 whitespace-nowrap">
                <Seal />
              </span>
              <span className="text-muted">Đề đã duyệt và được khoá.</span>
            </div>
          ) : (
            <p className="rounded-sm border border-warn/40 bg-warn/10 px-3 py-2 text-warn">
              Đề chưa duyệt nên bản xem trước có hình mờ “BẢN NHÁP”. Duyệt ở bước 4 để tải file.{" "}
              <Link to={`/exams/${exam.id}`} className="underline">
                Về bước Duyệt
              </Link>
            </p>
          )}
          <Button className="h-11 w-full" disabled={!approved || action.busy} onClick={() => get("student", "de-hoc-sinh.docx")}>
            Tải bản học sinh (.docx)
          </Button>
          <Button variant="outline" className="h-11 w-full" disabled={!approved || action.busy} onClick={() => get("teacher", "de-giao-vien.docx")}>
            Tải bản giáo viên (.docx)
          </Button>
          <FormError error={action.error} />
          <table className="w-full border-collapse">
            <tbody className="tabular-nums">
              {[
                ["Phiên bản đang xem", teacher ? "Giáo viên" : "Học sinh"],
                ["Số trang", pageCount || "…"],
                ["Số câu", `${exam.questions.length} (${count("multiple_choice")} · ${count("true_false")} · ${count("short_answer")})`],
                ["Thời gian", `${exam.duration_minutes} phút`],
                ["Khổ giấy · phông", "A4 · Times 12 pt"],
              ].map(([k, v]) => (
                <tr key={k}>
                  <td className="border-b border-line py-1.5 text-muted">{k}</td>
                  <td className="border-b border-line py-1.5 text-right font-medium">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-muted">
            Bản giáo viên có thêm đáp án, lời giải từng bước và bảng đáp án cuối đề. Nạp đề vào ngân hàng do quản trị viên thực hiện.
            {user?.role === "admin" && (
              <>
                {" "}
                <Link to="/admin/bank" className="text-accent underline">
                  Đến Quản trị ngân hàng
                </Link>
              </>
            )}
          </p>
          <Link to={`/exams?exam=${exam.id}`} className="block text-accent">
            ← Về danh sách đề
          </Link>
        </aside>
      </div>

      {/* Hidden copy at the printable width, used only to measure block heights. */}
      <div
        ref={measureRef}
        aria-hidden
        className={cn("invisible absolute top-0 -left-[10000px] text-[16px] leading-normal", PAPER_FONT)}
        style={{ width: SHEET_W - 2 * PAD_X }}
      >
        {keyed(blocks, "b").map(({ id, value: b }) => (
          <div key={id} className="pb-2">
            {b.node}
          </div>
        ))}
      </div>
    </section>
  );
}

