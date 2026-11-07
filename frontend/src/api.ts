import type { TokenPair } from "./types";

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const PREFIX = "/api/v1";
const TOKENS_KEY = "edugen.tokens";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly messages: string[],
  ) {
    super(messages.join("; ") || `Lỗi ${status}`);
  }
}

function loadTokens(): TokenPair | null {
  try {
    const raw = localStorage.getItem(TOKENS_KEY);
    return raw ? (JSON.parse(raw) as TokenPair) : null;
  } catch {
    return null;
  }
}

let tokens: TokenPair | null = loadTokens();

export function setTokens(next: TokenPair | null): void {
  tokens = next;
  try {
    if (next) localStorage.setItem(TOKENS_KEY, JSON.stringify(next));
    else localStorage.removeItem(TOKENS_KEY);
  } catch {
    // không lưu được (chế độ riêng tư): vẫn dùng trong bộ nhớ
  }
}

export function getRefreshToken(): string | null {
  return tokens?.refresh_token ?? null;
}

export const GENERIC_ERROR = "Không thực hiện được thao tác. Vui lòng thử lại.";

// `detail` của FastAPI: chuỗi, danh sách chuỗi (lỗi nghiệp vụ) hoặc danh sách lỗi validate {loc, msg}.
function messagesOf(detail: unknown): string[] {
  if (detail == null) return [];
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      if (typeof d === "string") return d;
      if (d && typeof d === "object" && "msg" in d) {
        const loc = Array.isArray((d as { loc?: unknown[] }).loc) ? (d as { loc: unknown[] }).loc.slice(1).join(".") : "";
        return loc ? `${loc}: ${(d as { msg: string }).msg}` : (d as { msg: string }).msg;
      }
      return GENERIC_ERROR;
    });
  }
  return [GENERIC_ERROR];
}

async function errorOf(resp: Response): Promise<ApiError> {
  let detail: unknown = resp.statusText;
  try {
    detail = ((await resp.json()) as { detail?: unknown }).detail ?? detail;
  } catch {
    // body không phải JSON
  }
  return new ApiError(resp.status, messagesOf(detail));
}

let refreshing: Promise<boolean> | null = null;

async function refresh(): Promise<boolean> {
  const refreshToken = tokens?.refresh_token;
  if (!refreshToken) return false;
  refreshing ??= (async () => {
    try {
      const resp = await fetch(API_URL + PREFIX + "/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!resp.ok) {
        setTokens(null);
        return false;
      }
      setTokens((await resp.json()) as TokenPair);
      return true;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

interface Options {
  method?: string;
  json?: unknown;
  form?: FormData;
}

async function send(path: string, opts: Options, retry = true): Promise<Response> {
  const headers: Record<string, string> = {};
  if (tokens) headers.Authorization = `Bearer ${tokens.access_token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  const resp = await fetch(API_URL + PREFIX + path, { method: opts.method ?? "GET", headers, body });
  if (resp.status === 401 && retry && (await refresh())) return send(path, opts, false);
  if (!resp.ok) throw await errorOf(resp);
  return resp;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const resp = await send(path, opts);
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// Tải file (DOCX): tên file lấy từ Content-Disposition (filename*=UTF-8''...).
export async function download(path: string, fallbackName: string): Promise<void> {
  const resp = await send(path, {});
  const disposition = resp.headers.get("Content-Disposition") ?? "";
  const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
