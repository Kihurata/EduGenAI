import { memo, useEffect, useState } from "react";

import { api } from "@/api";
import { keyed, MathText, QuestionStem, useAction } from "@/common";
import { Chip } from "@/components/Chip";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { TYPE_LABEL, type Question, type QuestionContent } from "@/types";

import { FormError, LETTERS, mathOption, optionColumns, solutionSteps, taClass } from "./lib";

interface Props {
  examId: string;
  question: Question;
  number: number;
  locked: boolean;
  showKey: boolean;
  solutionsOpen: boolean;
  active: boolean;
  onChanged: () => void;
}

/** One question inside the continuous review document, with answer, step-by-step solution and edit / regenerate / delete. */
export default function QuestionPanel({ examId, question, number, locked, showKey, solutionsOpen, active, onChanged }: Readonly<Props>) {
  const [editing, setEditing] = useState(false);
  const [showSolution, setShowSolution] = useState(solutionsOpen);
  const [asking, setAsking] = useState(false);
  const action = useAction();
  const q = question.content;
  const base = `/exams/${examId}/questions/${question.id}`;

  useEffect(() => setShowSolution(solutionsOpen), [solutionsOpen]);

  async function remove() {
    setAsking(false);
    // API: DELETE /api/v1/exams/{id}/questions/{qid}
    if ((await action.run(() => api(base, { method: "DELETE" }))) !== undefined) onChanged();
  }

  async function regenerate() {
    // API: POST /api/v1/exams/{id}/questions/{qid}/regenerate
    if ((await action.run(() => api(`${base}/regenerate`, { method: "POST" }))) !== undefined) onChanged();
  }

  if (editing) {
    return (
      <div className="rounded-sm border border-accent/40 bg-surface p-4 font-sans">
        <QuestionEditor
          initial={q}
          number={number}
          onCancel={() => setEditing(false)}
          onSave={async (content) => {
            // API: PUT /api/v1/exams/{id}/questions/{qid}
            const saved = await action.run(() => api(base, { method: "PUT", json: content }));
            if (saved !== undefined) {
              setEditing(false);
              onChanged();
            }
          }}
          busy={action.busy}
          error={action.error}
        />
      </div>
    );
  }

  const steps = solutionSteps(q.solution ?? "");
  const tfKey = q.statements?.map((s, i) => `${"abcd"[i]}) ${s.correct ? "Đ" : "S"}`).join(" · ");
  const cols = q.options ? optionColumns(q.options) : 1;

  return (
    <article className="group">
      <header className="mb-1 flex flex-wrap items-center gap-2 font-sans text-xs">
        <Chip>{q.level}</Chip>
        {question.edited && <Chip tone="accent">GV đã sửa</Chip>}
        {!locked && (
          <span className={cn("ml-auto flex gap-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100", active && "opacity-100")}>
            {asking ? (
              <>
                <Button variant="danger" className="h-7" onClick={remove}>
                  Chắc chắn xoá
                </Button>
                <Button variant="ghost" className="h-7" onClick={() => setAsking(false)}>
                  Huỷ
                </Button>
              </>
            ) : (
              <>
                <Button variant="ghost" className="h-7 text-muted hover:bg-soft hover:text-ink" onClick={() => setEditing(true)} disabled={action.busy}>
                  Sửa
                </Button>
                <Button variant="ghost" className="h-7 text-muted hover:bg-soft hover:text-ink" onClick={regenerate} disabled={action.busy}>
                  {action.busy ? "Đang sinh lại…" : "Sinh lại"}
                </Button>
                <Button variant="ghost" className="h-7 text-muted hover:bg-soft hover:text-son" onClick={() => setAsking(true)} disabled={action.busy}>
                  Xoá
                </Button>
              </>
            )}
          </span>
        )}
      </header>

      <div className="leading-relaxed">
        <strong>Câu {number}.</strong> <QuestionStem stem={q.stem} table={q.table} />
      </div>

      {q.type === "multiple_choice" && q.options && (
        <ol className={cn("mt-2 grid gap-x-4 gap-y-1", cols === 4 ? "sm:grid-cols-4" : cols === 2 ? "sm:grid-cols-2" : "")}>
          {q.options.map((opt, i) => (
            <li key={LETTERS[i]} className={cn("rounded-sm border border-transparent px-2 py-0.5", showKey && q.answer === LETTERS[i] && "border-ok/50 bg-ok/10")}>
              <strong>{LETTERS[i]}.</strong> <MathText text={mathOption(opt)} />
            </li>
          ))}
        </ol>
      )}

      {q.type === "true_false" && q.statements && (
        <ol className="mt-2 space-y-1">
          {q.statements.map((s, i) => (
            <li key={"abcd"[i]} className="grid grid-cols-[1.6rem_minmax(0,1fr)_auto] gap-1 px-2">
              <strong>{"abcd"[i]})</strong>
              <span>
                <MathText text={s.text} />
              </span>
              {showKey && <span className={cn("font-sans text-xs font-semibold", s.correct ? "text-ok" : "text-bad")}>{s.correct ? "Đúng" : "Sai"}</span>}
            </li>
          ))}
        </ol>
      )}

      {showKey && (
        <p className="mt-2 flex flex-wrap items-center gap-3 font-sans text-sm">
          <span>
            {q.type === "short_answer" ? "Đáp số" : "Đáp án"}: <strong>{q.type === "true_false" ? tfKey : q.answer}</strong>
          </span>
          <button type="button" className="cursor-pointer text-accent hover:underline" aria-expanded={showSolution} onClick={() => setShowSolution((v) => !v)}>
            {showSolution ? "Ẩn lời giải" : "Xem lời giải"}
          </button>
        </p>
      )}
      {showKey && showSolution && (
        <div className="mt-2 border-l-2 border-accent bg-paper/70 px-4 py-2.5">
          <p className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-accent">Lời giải</p>
          <ol className="list-decimal space-y-1 pl-5 marker:font-sans marker:text-xs marker:text-muted">
            {keyed(steps, "st").map(({ id, value: step }) => (
              <li key={id}>
                <MathText text={step} />
              </li>
            ))}
            {q.type === "true_false" &&
              q.statements?.map(
                (s, i) =>
                  s.explanation && (
                    <li key={`s-${"abcd"[i]}`}>
                      <strong>
                        {"abcd"[i]}) {s.correct ? "Đúng" : "Sai"}.
                      </strong>{" "}
                      <MathText text={s.explanation} />
                    </li>
                  ),
              )}
          </ol>
        </div>
      )}

      <FormError error={action.error} />
    </article>
  );
}

interface EditorProps {
  initial: QuestionContent;
  number: number;
  busy: boolean;
  error: unknown;
  onCancel: () => void;
  onSave: (content: QuestionContent) => void;
}

// Manual edit: sends the whole question in the BE format; BE re-validates structure and asks RAG to check content.
const SNIPPETS: [string, string][] = [
  ["Phân số", String.raw`$\frac{a}{b}$`],
  ["Căn", String.raw`$\sqrt{x}$`],
  ["Mũ", "$x^{2}$"],
  ["Chỉ số", "$x_{1}$"],
];

/** Live preview of a text field, rendered with the same MathText as the question view. */
const Preview = memo(function Preview({ text }: Readonly<{ text: string }>) {
  if (!text.trim()) return null;
  return (
    <div className="border-l-2 border-line pl-3 text-sm" aria-label="Xem trước">
      <MathText text={text} />
    </div>
  );
});

function MathHelp({ onInsert }: Readonly<{ onInsert: (snippet: string) => void }>) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
      <span>Công thức đặt trong $...$, ví dụ $x^2$. Chèn nhanh:</span>
      {SNIPPETS.map(([label, snippet]) => (
        <button key={label} type="button" className="cursor-pointer rounded-sm border border-line px-2 py-0.5 hover:text-ink" onClick={() => onInsert(snippet)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function QuestionEditor({ initial, number, busy, error, onCancel, onSave }: Readonly<EditorProps>) {
  const [q, setQ] = useState<QuestionContent>(() => structuredClone(initial));
  const set = (patch: Partial<QuestionContent>) => setQ((prev) => ({ ...prev, ...patch }));

  function save() {
    const content = { ...q };
    if (q.type === "true_false" && q.statements) {
      content.answer = q.statements.map((s) => (s.correct ? "Đ" : "S")).join("");
    }
    onSave(content);
  }

  return (
    <article className="space-y-4">
      <header className="flex flex-wrap items-center gap-2 text-sm">
        <strong className="text-base">Sửa câu {number}</strong>
        <Chip>{TYPE_LABEL[q.type]}</Chip>
        <Chip>{q.level}</Chip>
      </header>
      <label className="block text-sm">
        <span className="mb-1 block text-muted">Đề bài (LaTeX trong $...$)</span>
        <textarea className={taClass} rows={4} value={q.stem} onChange={(e) => set({ stem: e.target.value })} />
      </label>
      <MathHelp onInsert={(sn) => set({ stem: q.stem + sn })} />
      {q.stem.trim() && (
        <div className="border-l-2 border-line pl-3 text-sm" aria-label="Xem trước">
          <QuestionStem stem={q.stem} table={q.table} />
        </div>
      )}

      {q.type === "multiple_choice" && q.options && (
        <div className="space-y-2">
          {q.options.map((opt, i) => (
            <div key={LETTERS[i]} className="space-y-1">
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" name="answer" checked={q.answer === LETTERS[i]} onChange={() => set({ answer: LETTERS[i] })} />
                {LETTERS[i]}.
                <Input value={opt} onChange={(e) => set({ options: q.options!.map((o, j) => (j === i ? e.target.value : o)) })} />
              </label>
              <div className="pl-8">
                <Preview text={mathOption(opt)} />
              </div>
            </div>
          ))}
          <p className="text-xs text-muted">Chọn nút tròn ở phương án đúng.</p>
        </div>
      )}

      {q.type === "true_false" && q.statements && (
        <div className="space-y-3">
          {q.statements.map((s, i) => (
            <div key={"abcd"[i]} className="space-y-1">
              <label className="flex items-center gap-2 text-sm">
                {"abcd"[i]})
                <Input
                  value={s.text}
                  onChange={(e) => set({ statements: q.statements!.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })}
                />
                <Select
                  className="w-28"
                  value={s.correct ? "Đ" : "S"}
                  onChange={(e) =>
                    set({ statements: q.statements!.map((x, j) => (j === i ? { ...x, correct: e.target.value === "Đ" } : x)) })
                  }
                >
                  <option value="Đ">Đúng</option>
                  <option value="S">Sai</option>
                </Select>
              </label>
              <Preview text={mathOption(s.text)} />
              <Input
                placeholder="Giải thích ý này"
                value={s.explanation}
                onChange={(e) =>
                  set({ statements: q.statements!.map((x, j) => (j === i ? { ...x, explanation: e.target.value } : x)) })
                }
              />
              <Preview text={s.explanation} />
            </div>
          ))}
        </div>
      )}

      {q.type === "short_answer" && (
        <label className="block text-sm">
          <span className="mb-1 block text-muted">Đáp án (tối đa 4 ký tự, ví dụ 7,07)</span>
          <Input className="w-32" value={q.answer} onChange={(e) => set({ answer: e.target.value })} />
        </label>
      )}

      <label className="block text-sm">
        <span className="mb-1 block text-muted">Lời giải</span>
        <textarea className={taClass} rows={5} value={q.solution} onChange={(e) => set({ solution: e.target.value })} />
      </label>
      <MathHelp onInsert={(sn) => set({ solution: q.solution + sn })} />
      <Preview text={q.solution} />

      <FormError error={error} />
      <footer className="flex gap-2">
        <Button variant="outline" onClick={onCancel} disabled={busy}>
          Huỷ
        </Button>
        <Button onClick={save} disabled={busy}>
          {busy ? "Đang kiểm câu…" : "Lưu câu"}
        </Button>
      </footer>
    </article>
  );
}
