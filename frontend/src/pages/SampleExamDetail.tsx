// Tóm tắt: trang duyệt một đề mẫu (T-050): GV xem bản nháp BE đọc được, sửa thông tin đề (tên, mã đề, lớp, loại đề)
// và từng câu (phần, đề bài, phương án, đáp án, chủ đề, mức độ), lưu để BE kiểm tra lại, hết lỗi thì xác nhận cho RAG
// học. Môn, official và trường do hệ thống gắn nên không có ô sửa.
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { Badge, ErrorBox, keyed, QuestionStem, useAction, usePolling } from "../common";
import { subjectLabel, useSubjects } from "../subjects";
import {
  EXAM_KINDS,
  LEVELS,
  type DraftIssue,
  type DraftQuestion,
  type ExamDraft,
  type Part,
  type SampleExam,
  type TopicOption,
} from "../types";

const OPTIONS = ["A", "B", "C", "D"];
const LABELS = ["a", "b", "c", "d"];
const PART_LABEL: Record<Part, string> = { I: "I · Nhiều lựa chọn", II: "II · Đúng/Sai", III: "III · Trả lời ngắn" };

function keyOf(q: DraftQuestion): string {
  return `${q.part}-${q.cau}`;
}

// Đổi phần thì thêm các trường phần mới cần, để GV chỉ phải điền nội dung.
function withPart(q: DraftQuestion, part: Part): DraftQuestion {
  const next: DraftQuestion = { ...q, part };
  if (part === "I") next.options ??= Object.fromEntries(OPTIONS.map((o) => [o, ""]));
  if (part === "II") next.statements ??= LABELS.map((label) => ({ label, text: "", answer: null }));
  return next;
}

export default function SampleExamDetail() {
  const { id } = useParams();
  const subjects = useSubjects();
  const [sample, setSample] = useState<SampleExam | null>(null);
  const [draft, setDraft] = useState<ExamDraft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [topics, setTopics] = useState<TopicOption[]>([]);
  const load = useAction();
  const save = useAction();
  const confirm = useAction();

  const show = useCallback((s: SampleExam) => {
    setSample(s);
    setDraft(s.draft ? structuredClone(s.draft) : null);
    setDirty(false);
  }, []);
  const reload = useCallback(() => {
    void load.run(async () => show(await api<SampleExam>(`/admin/sample-exams/${id}`)));
  }, [id, show]);
  useEffect(reload, [reload]);
  usePolling(reload, !dirty && (sample?.status === "pending" || sample?.status === "sent"));
  useEffect(() => {
    if (sample) void api<TopicOption[]>(`/topics?subject=${sample.subject}`).then(setTopics, () => setTopics([]));
  }, [sample?.subject]);

  if (!sample) return load.error ? <ErrorBox error={load.error} /> : <p className="text-sm text-muted">Đang tải…</p>;

  function edit(change: (d: ExamDraft) => void) {
    setDraft((d) => {
      if (!d) return d;
      const next = structuredClone(d);
      change(next);
      return next;
    });
    setDirty(true);
  }
  const editQuestion = (i: number, change: (q: DraftQuestion) => DraftQuestion | void) =>
    edit((d) => {
      d.questions[i] = change(d.questions[i]) ?? d.questions[i];
    });

  async function saveDraft() {
    const saved = await save.run(() =>
      api<SampleExam>(`/admin/sample-exams/${id}/draft`, { method: "PUT", json: { draft } }),
    );
    if (saved) show(saved);
  }
  async function confirmDraft() {
    const done = await confirm.run(() => api<SampleExam>(`/admin/sample-exams/${id}/confirm`, { method: "POST" }));
    if (done) show(done);
  }

  const byQuestion = new Map<string, DraftIssue[]>();
  for (const issue of sample.issues) {
    const k = issue.question ?? "";
    byQuestion.set(k, [...(byQuestion.get(k) ?? []), issue]);
  }
  const usable = topics.filter((t) => t.grade <= (draft?.grade ?? sample.grade));

  return (
    <>
      <Link className="back" to="/sample-exams">
        ← Đề mẫu
      </Link>
      <div className="page-head">
        <h1 className="text-xl font-semibold">{sample.title}</h1>
        <Badge status={sample.status} />
      </div>
      <p className="muted">
        {subjectLabel(subjects, sample.subject)} · lớp {sample.grade} · {sample.original_filename} · không chính
        thức (đề trường tải lên)
      </p>
      {sample.status === "pending" && <p className="notice">Đang đọc đề thành bản nháp…</p>}
      {sample.error_message && <ErrorBox error={sample.error_message} />}

      {draft && (
        <>
          <div className="card">
            <strong>Thông tin đề</strong>
            <div className="meta-row">
              <label>
                <span>Tên đề</span>
                <input value={draft.exam ?? ""} onChange={(e) => edit((d) => { d.exam = e.target.value; })} />
              </label>
              <label>
                <span>Mã đề</span>
                <input value={draft.ma_de ?? ""} onChange={(e) => edit((d) => { d.ma_de = e.target.value; })} />
              </label>
              <label>
                <span>Lớp</span>
                <select
                  value={draft.grade ?? sample.grade}
                  onChange={(e) => edit((d) => { d.grade = Number(e.target.value); })}
                >
                  {[10, 11, 12].map((g) => (
                    <option key={g}>{g}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Loại đề</span>
                <select
                  value={draft.exam_kind ?? ""}
                  onChange={(e) => edit((d) => { d.exam_kind = e.target.value || null; })}
                >
                  <option value="">(chưa chọn)</option>
                  {Object.entries(EXAM_KINDS).map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {(byQuestion.get("") ?? []).map((i) => (
              <p key={i.message} className="notice warn">
                {i.message}
              </p>
            ))}
          </div>

          {keyed(draft.questions, "q").map(({ id, value: q }, i) => (
            <QuestionEditor
              key={id}
              q={q}
              topics={usable}
              issues={byQuestion.get(keyOf(q)) ?? []}
              onChange={(change) => editQuestion(i, change)}
              onRemove={() => edit((d) => { d.questions.splice(i, 1); })}
            />
          ))}

          <div className="actions">
            <button
              type="button"
              className="ghost"
              onClick={() =>
                edit((d) => {
                  d.questions.push(withPart({ part: "I", cau: d.questions.filter((x) => x.part === "I").length + 1, stem: "" }, "I"));
                })
              }
            >
              + Thêm câu
            </button>
            <button type="button" className="primary" disabled={!dirty || save.busy} onClick={() => void saveDraft()}>
              {save.busy ? "Đang lưu…" : "Lưu và kiểm tra"}
            </button>
            <button
              type="button"
              className="primary"
              disabled={dirty || sample.issues.length > 0 || confirm.busy || sample.status === "sent"}
              title={dirty ? "Lưu trước" : sample.issues.length ? "Còn lỗi cần sửa" : ""}
              onClick={() => void confirmDraft()}
            >
              {confirm.busy ? "Đang gửi…" : sample.status === "ingested" ? "Nạp lại cho RAG" : "Xác nhận cho RAG học"}
            </button>
            <span className="muted">
              {dirty ? "Có thay đổi chưa lưu" : `${sample.issues.length} lỗi cần sửa`}
            </span>
          </div>
          <ErrorBox error={save.error ?? confirm.error} />
        </>
      )}
    </>
  );
}

function QuestionEditor({
  q,
  topics,
  issues,
  onChange,
  onRemove,
}: Readonly<{
  q: DraftQuestion;
  topics: TopicOption[];
  issues: DraftIssue[];
  onChange: (change: (q: DraftQuestion) => DraftQuestion | void) => void;
  onRemove: () => void;
}>) {
  const set = (field: string, value: unknown) => onChange((x) => ({ ...x, [field]: value }));
  const known = topics.some((t) => t.code === q.topic);
  return (
    <div className="card">
      <div className="meta-row">
        <label>
          <span>Phần</span>
          <select value={q.part} onChange={(e) => onChange((x) => withPart(x, e.target.value as Part))}>
            {(Object.keys(PART_LABEL) as Part[]).map((p) => (
              <option key={p} value={p}>
                {PART_LABEL[p]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Câu</span>
          <input type="number" min={1} value={q.cau} onChange={(e) => set("cau", Number(e.target.value))} />
        </label>
        <label>
          <span>Chủ đề</span>
          <select value={known ? q.topic : ""} onChange={(e) => set("topic", e.target.value)}>
            <option value="">(chưa chọn)</option>
            {topics.map((t) => (
              <option key={t.code} value={t.code}>
                Lớp {t.grade} · {t.name}
              </option>
            ))}
          </select>
        </label>
        {q.part !== "II" && (
          <label>
            <span>Mức độ</span>
            <select value={q.level ?? ""} onChange={(e) => set("level", e.target.value || null)}>
              <option value="">(không ghi)</option>
              {LEVELS.map((lv) => (
                <option key={lv}>{lv}</option>
              ))}
            </select>
          </label>
        )}
        <button type="button" className="danger ghost" onClick={onRemove}>
          Xoá câu
        </button>
      </div>
      {issues.map((i) => (
        <p key={i.message} className="notice warn">
          {i.message}
        </p>
      ))}

      <label>
        <span>Đề bài</span>
        <textarea rows={3} value={q.stem ?? ""} onChange={(e) => set("stem", e.target.value)} />
      </label>
      <div className="preview">
        <QuestionStem stem={q.stem ?? ""} table={q.table} />
      </div>
      <label>
        <span>Mô tả hình (nếu có)</span>
        <input value={q.figure ?? ""} onChange={(e) => set("figure", e.target.value || undefined)} />
      </label>

      {q.part === "I" && (
        <div className="options">
          {OPTIONS.map((o) => (
            <label key={o} className="option-row">
              <input
                type="radio"
                name={`answer-${q.part}-${q.cau}`}
                checked={q.answer === o}
                onChange={() => set("answer", o)}
              />
              {o}.
              <input value={q.options?.[o] ?? ""} onChange={(e) => set("options", { ...q.options, [o]: e.target.value })} />
            </label>
          ))}
        </div>
      )}

      {q.part === "II" && (
        <div className="statements">
          {(q.statements ?? []).map((s, k) => (
            <div key={s.label} className="statement-edit">
              {s.label})
              <input
                value={s.text}
                onChange={(e) =>
                  onChange((x) => ({ ...x, statements: x.statements?.map((t, j) => (j === k ? { ...t, text: e.target.value } : t)) }))
                }
              />
              <select
                value={s.answer === null || s.answer === undefined ? "" : String(s.answer)}
                onChange={(e) =>
                  onChange((x) => ({
                    ...x,
                    statements: x.statements?.map((t, j) => (j === k ? { ...t, answer: e.target.value === "" ? null : e.target.value === "true" } : t)),
                  }))
                }
              >
                <option value="">(đáp án)</option>
                <option value="true">Đúng</option>
                <option value="false">Sai</option>
              </select>
              <select
                value={q.statement_levels?.[k] ?? ""}
                onChange={(e) =>
                  onChange((x) => {
                    const levels = [...(x.statement_levels ?? ["", "", "", ""])];
                    levels[k] = e.target.value as (typeof levels)[number];
                    return { ...x, statement_levels: levels.every((lv) => !lv) ? null : levels };
                  })
                }
              >
                <option value="">(mức độ)</option>
                {LEVELS.map((lv) => (
                  <option key={lv}>{lv}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {q.part === "III" && (
        <label>
          <span>Đáp án (một con số, dấu phẩy thập phân)</span>
          <input value={q.answer ?? ""} placeholder="vd: -1,5" onChange={(e) => set("answer", e.target.value)} />
        </label>
      )}
    </div>
  );
}
