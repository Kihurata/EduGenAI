import katex from "katex";
import { Fragment, useEffect, useRef, useState } from "react";

import { ApiError, GENERIC_ERROR } from "./api";
import { stemBlocks } from "./lib/table";

// Văn bản có công thức LaTeX $...$ / $$...$$ (format câu hỏi của RAG). Phần chữ do React escape;
// chỉ phần công thức đi qua KaTeX (trust: false mặc định).
const MATH = /(\$\$[\s\S]+?\$\$|\$[^$]+?\$)/g;

// Hình khối BE đã vẽ sẵn (`figure_svg`, app/domain/figure.py) hiện bằng <img> data URL: ảnh SVG không chạy được script,
// nên không cần dangerouslySetInnerHTML. `caption` (mô tả chữ `figure`) làm alt; không có SVG thì không hiện gì.
export function QuestionFigure({ svg, caption }: Readonly<{ svg?: string; caption?: string }>) {
  if (!svg) return null;
  return (
    <img
      data-testid="question-figure"
      className="my-2 h-auto max-w-full bg-white"
      src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`}
      alt={caption || "Hình vẽ"}
    />
  );
}

// Đề bài + bảng (trường `table` hoặc bảng markdown trong đề) thành bảng thật; ô vẫn render công thức.
export function QuestionStem({ stem, table }: Readonly<{ stem: string; table?: unknown }>) {
  return (
    <>
      {keyed(stemBlocks(stem, table), "b").map(({ id, value: b }) =>
        "text" in b ? (
          <MathText key={id} text={b.text} />
        ) : (
          <table key={id} className="my-2 border-collapse text-center" data-testid="question-table">
            <tbody>
              {keyed(b.table, "r").map(({ id: rowId, value: row }) => (
                <tr key={rowId}>
                  {keyed(row, "c").map(({ id: cellId, value: cell }) => {
                    const Cell = rowId === "r0" ? "th" : "td";
                    return (
                      <Cell key={cellId} className="border border-black px-3 py-1 font-normal">
                        <MathText text={cell} />
                      </Cell>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        ),
      )}
    </>
  );
}

// Khóa React cho khối/hàng/ô của đề: nội dung tĩnh theo câu, không thêm/xóa/đổi chỗ, nên vị trí là định danh.
export function keyed<T>(items: readonly T[], prefix: string): { id: string; value: T }[] {
  return items.map((value, n) => ({ id: `${prefix}${n}`, value }));
}

// `\inf` prints the word "inf" (the model meant `\infty`); a sign followed by bare "inf" is the same slip.
const BARE_INF = /\\inf(?![a-zA-Z]|\s*(?:_|\\limits))|(?<=[-+])inf(?![a-zA-Z])/g;

/** Fix infinity written as `\inf`/"-inf", and wrap a `\infty` left outside $...$ so it renders as math. */
export function fixInfinity(text: string): string {
  return text
    .replace(BARE_INF, "\\infty")
    .split(MATH)
    .map((part, i) => (i % 2 === 1 ? part : part.replace(/([-+]?)\s*\\infty/g, "$$$1\\infty$$")))
    .join("");
}

export function MathText({ text: raw }: Readonly<{ text: string }>) {
  const text = fixInfinity(raw);
  const parts = text.split(MATH);
  return (
    <span className="math-text">
      {parts.map((part, i) => {
        if (i % 2 === 1) {
          const display = part.startsWith("$$");
          const tex = part.slice(display ? 2 : 1, display ? -2 : -1);
          const html = katex.renderToString(tex, { displayMode: display, throwOnError: false });
          return <span key={i} dangerouslySetInnerHTML={{ __html: html }} />;
        }
        const lines = part.split("\n");
        return (
          <Fragment key={i}>
            {lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {line}
              </Fragment>
            ))}
          </Fragment>
        );
      })}
    </span>
  );
}

const STATUS_LABEL: Record<string, string> = {
  uploaded: "Đã tải lên",
  converting: "Đang đọc ảnh",
  parsed: "Đã đọc",
  invalid: "Có lỗi",
  confirmed: "Đã xác nhận",
  failed: "Lỗi",
  generating: "Đang sinh",
  generated: "Đã sinh",
  incomplete: "Thiếu câu",
  approved: "Đã duyệt",
  complete: "Đủ câu",
  short: "Thiếu",
  error: "Lỗi",
  pending: "Chờ gửi",
  needs_review: "Chờ duyệt",
  sent: "Đã gửi RAG",
  ingested: "RAG đã học",
};

const STATUS_TONE: Record<string, string> = {
  confirmed: "ok",
  approved: "ok",
  complete: "ok",
  ingested: "ok",
  generated: "info",
  parsed: "info",
  sent: "info",
  uploaded: "busy",
  converting: "busy",
  generating: "busy",
  pending: "busy",
  invalid: "warn",
  needs_review: "warn",
  incomplete: "warn",
  short: "warn",
  failed: "bad",
  error: "bad",
};

export function Badge({ status }: Readonly<{ status: string }>) {
  return <span className={`badge ${STATUS_TONE[status] ?? ""}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function ErrorBox({ error }: Readonly<{ error: unknown }>) {
  if (!error) return null;
  let messages: string[];
  if (error instanceof ApiError) messages = error.messages;
  else if (error instanceof Error) messages = [error instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(error.message) ? GENERIC_ERROR : error.message];
  else messages = [typeof error === "string" ? error : GENERIC_ERROR];
  return (
    <div className="error-box" role="alert">
      {messages.length === 1 ? messages[0] : (
        <ul>
          {messages.map((m, i) => (
            <li key={i}>{m}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Gọi lại `load` mỗi `ms` khi `active` (job nền của BE: đọc ma trận, sinh đề).
export function usePolling(load: () => void, active: boolean, ms = 2000): void {
  const ref = useRef(load);
  ref.current = load;
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => ref.current(), ms);
    return () => window.clearInterval(id);
  }, [active, ms]);
}

// Chạy một thao tác bất đồng bộ, giữ trạng thái đang chạy và lỗi cho nút bấm.
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}

// BE trả thời gian UTC không có hậu tố múi giờ.
export function formatTime(iso: string): string {
  const d = new Date(/(?:[zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : iso + "Z");
  return d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

// Nút xoá hai bước, không dùng hộp thoại confirm của trình duyệt.
export function ConfirmButton({
  label,
  onConfirm,
  disabled,
}: Readonly<{ label: string; onConfirm: () => void; disabled?: boolean }>) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <button type="button" className="danger ghost" disabled={disabled} onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  }
  return (
    <span className="confirm">
      <button
        type="button"
        className="danger"
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        Chắc chắn {label.toLowerCase()}
      </button>
      <button type="button" className="ghost" onClick={() => setAsking(false)}>
        Huỷ
      </button>
    </span>
  );
}
