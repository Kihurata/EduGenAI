import { delay } from "@/lib/mock";
import type { Coverage, CoverageCheck, NewSource, Source } from "./types";

let sources: Source[] = [
  { id: "s1", name: "SGK Toán 12 – Kết nối tri thức", kind: "sgk", subject: "Toán", grade: 12, official: true, status: "loaded" },
  { id: "s2", name: "SGK Vật lí 12 – Kết nối tri thức", kind: "sgk", subject: "Lý", grade: 12, official: true, status: "loaded" },
  { id: "s3", name: "SGK Hóa học 12 – Kết nối tri thức", kind: "sgk", subject: "Hóa", grade: 12, official: true, status: "loading" },
  { id: "s4", name: "Đề minh họa 2025 – Toán", kind: "de", subject: "Toán", grade: 12, official: true, status: "loaded" },
  { id: "s5", name: "SGK Sinh học 12 – Kết nối tri thức", kind: "sgk", subject: "Sinh", grade: 12, official: true, status: "pending" },
  { id: "s6", name: "Đề thi thử Hóa – Sở GD (bản scan)", kind: "de", subject: "Hóa", grade: 12, official: false, status: "failed" },
];

// TODO(BE): GET /api/v1/admin/sources
//   req : -
//   res : [{ id, name, kind: "sgk"|"de", subject, grade, official, status: "loaded"|"loading"|"pending"|"failed" }]
//   owner: Backend (Huy/Phu) + RAG (Dong Quan) · feature: Khối 1 nguồn tài liệu · now: mock in features/admin/sources/mock.ts
export const getSources = () => delay([...sources]);

// TODO(BE): POST /api/v1/admin/sources (multipart: file + manifest entry {name, kind, subject, grade, official})
//   req : file=<pdf|json|yaml>, manifest={ name, kind, subject, grade, official }
//   res : Source (status "pending")
//   owner: Backend (Huy/Phu) + RAG (Dong Quan) · feature: Khối 1 nguồn tài liệu · now: mock in features/admin/sources/mock.ts
export async function createSource(n: NewSource): Promise<Source> {
  const s: Source = { id: `s${Date.now()}`, name: n.name, kind: n.kind, subject: n.subject, grade: n.grade, official: n.official, status: "pending" };
  sources = [...sources, s];
  return delay(s);
}

// TODO(BE): POST /api/v1/admin/sources/{id}/ingest
//   req : -
//   res : { id, status: "loading" } (202, runs chunk + embed + upsert in background)
//   owner: Backend (Huy/Phu) + RAG (Dong Quan) · feature: Khối 1 nguồn tài liệu · now: mock in features/admin/sources/mock.ts
export async function startIngest(id: string): Promise<Source> {
  return setStatus(id, "loading");
}

// TODO(BE): GET /api/v1/admin/sources/{id}/ingest-status
//   req : -
//   res : { id, status: "loaded"|"loading"|"failed", chunks: number, error?: string }
//   owner: Backend (Huy/Phu) + RAG (Dong Quan) · feature: Khối 1 nguồn tài liệu · now: mock finishes ingest after a delay
export async function finishIngest(id: string): Promise<Source> {
  return setStatus(id, "loaded");
}

function setStatus(id: string, status: Source["status"]): Promise<Source> {
  sources = sources.map((s) => (s.id === id ? { ...s, status } : s));
  return delay(sources.find((s) => s.id === id) as Source, 200);
}

// TODO(BE): GET /api/v1/admin/sources/coverage
//   req : -
//   res : { covered: number, total: number }  (lessons of the SGK outline with >=1 chunk)
//   owner: RAG (Dong Quan) · feature: Khối 1 độ phủ · now: mock in features/admin/sources/mock.ts
export async function getCoverage(): Promise<Coverage> {
  const loaded = sources.filter((s) => s.kind === "sgk" && s.status === "loaded").length;
  return delay({ covered: loaded * 14, total: 4 * 14 });
}

// TODO(BE): POST /api/v1/admin/sources/coverage/check (mirrors TC-017 coverage report)
//   req : -
//   res : { ok: boolean, missing: number }
//   owner: RAG (Dong Quan) · feature: Khối 1 độ phủ · now: mock in features/admin/sources/mock.ts
export async function runCoverageCheck(): Promise<CoverageCheck> {
  const c = await getCoverage();
  return delay({ ok: c.covered === c.total, missing: c.total - c.covered, ref: "TC-017" }, 600);
}
