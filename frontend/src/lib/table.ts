// Bảng trong câu hỏi: một dạng chuẩn = danh sách hàng (hàng đầu là header), như `table` của BE.
// Đây là bản TS của app/domain/question.py::stem_blocks; sửa một bên thì sửa cả hai.
export type TableRows = string[][];
export type StemBlock = { text: string } | { table: TableRows };

const SEPARATOR_CELL = /^:?-+:?$/;

// Vị trí ngay sau công thức $...$ / $$...$$ bắt đầu tại i (hết dòng nếu không đóng).
function mathEnd(t: string, i: number): number {
  const delim = t.startsWith("$$", i) ? "$$" : "$";
  const close = t.indexOf(delim, i + delim.length);
  return close < 0 ? t.length : close + delim.length;
}

// Tách một dòng theo `|`; `\|` là dấu `|` thường, `|` trong $...$ / $$...$$ được giữ.
function cells(line: string): string[] {
  const t = line.trim();
  const out: string[] = [];
  let buf = "";
  let i = 0;
  while (i < t.length) {
    const ch = t[i];
    if (ch === "\\" && t[i + 1] === "|") {
      buf += "|";
      i += 2;
    } else if (ch === "$") {
      const end = mathEnd(t, i);
      buf += t.slice(i, end);
      i = end;
    } else if (ch === "|") {
      out.push(buf.trim());
      buf = "";
      i++;
    } else {
      buf += ch;
      i++;
    }
  }
  out.push(buf.trim());
  if (t.startsWith("|")) out.shift();
  if (t.endsWith("|") && !t.endsWith(String.raw`\|`) && out.length) out.pop();
  return out;
}

function isSeparator(line: string): boolean {
  const c = cells(line);
  return line.includes("|") && c.length > 0 && c.every((x) => SEPARATOR_CELL.test(x));
}

export function stemBlocks(stem: string, field?: unknown): StemBlock[] {
  const lines = stem.split("\n");
  let blocks: StemBlock[] = [];
  let text: string[] = [];
  const flush = () => {
    const joined = text.join("\n").trim();
    if (joined) blocks.push({ text: joined });
    text = [];
  };
  let i = 0;
  while (i < lines.length) {
    if (lines[i].includes("|") && i + 1 < lines.length && isSeparator(lines[i + 1])) {
      flush();
      const rows = [cells(lines[i])];
      i += 2;
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(cells(lines[i]));
        i += 1;
      }
      blocks.push({ table: rows });
    } else {
      text.push(lines[i]);
      i += 1;
    }
  }
  flush();
  if (Array.isArray(field) && field.length) {
    const rows = field.filter(Array.isArray).map((r) => r.map(String));
    const texts = blocks.filter((b): b is { text: string } => "text" in b).map((b) => b.text);
    blocks = [...(texts.length ? [{ text: texts.join("\n") }] : []), { table: rows }];
  }
  return blocks;
}
