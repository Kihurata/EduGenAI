import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api } from "@/api";
import { useAuth } from "@/auth";
import { formatTime } from "@/common";
import { Chip, type ChipTone } from "@/components/Chip";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import type { Exam, UserRole } from "@/types";

const entries = [
  { to: "/matrices", title: "Sinh đề", hint: "Tải ma trận, sinh và duyệt đề thi." },
  { to: "/classes", title: "Chấm bài", hint: "Lớp, phiếu trả lời, quét và kết quả.", tag: "Bản mẫu" },
  { to: "/admin/teachers", title: "Quản trị", hint: "Tài khoản giáo viên.", admin: true },
];

const STATUS: Record<string, { label: string; tone: ChipTone }> = {
  generating: { label: "Đang sinh", tone: "accent" },
  generated: { label: "Đã sinh", tone: "muted" },
  incomplete: { label: "Thiếu câu", tone: "warn" },
  failed: { label: "Lỗi", tone: "bad" },
  approved: { label: "Đã duyệt", tone: "ok" },
};

function RecentExams() {
  const [items, setItems] = useState<Exam[] | null>(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(() => {
    setFailed(false);
    setItems(null);
    // API: GET /api/v1/exams
    api<Exam[]>("/exams").then(setItems).catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);

  if (failed) return <ErrorState message="Không tải được danh sách đề thi." onRetry={load} />;
  if (!items) return <p className="text-sm text-muted">Đang tải…</p>;
  if (items.length === 0) {
    return (
      <EmptyState title="Chưa có đề thi nào" hint="Bắt đầu bằng việc tải một ma trận.">
        <Link to="/matrices" className="text-accent underline">Tải ma trận</Link>
      </EmptyState>
    );
  }
  return (
    <ul className="divide-y divide-line border-y border-line">
      {items.slice(0, 5).map((e) => {
        const s = STATUS[e.status] ?? { label: e.status, tone: "muted" as ChipTone };
        return (
          <li key={e.id}>
            <Link to={`/exams/${e.id}`} className="flex items-center justify-between gap-4 py-3 hover:bg-soft">
              <span className="truncate">{e.title}</span>
              <span className="flex shrink-0 items-center gap-3 text-sm text-muted">
                <Chip tone={s.tone}>{s.label}</Chip>
                {formatTime(e.created_at)}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function Home() {
  const { user } = useAuth();
  return (
    <section>
      <h1 className="mb-6 text-xl font-semibold">Xin chào, {user?.full_name}</h1>
      <div className="grid gap-4 md:grid-cols-3">
        {entries.filter((e) => !e.admin || user?.role === "admin").map((e) => (
          <Link key={e.to} to={e.to} className="border border-line bg-surface p-5 hover:bg-soft">
            <p className="font-medium">{e.title}{"tag" in e && e.tag && <span className="ml-2 border border-line px-1.5 py-0.5 text-xs font-normal text-muted">{e.tag}</span>}</p>
            <p className="mt-1 text-sm text-muted">{e.hint}</p>
          </Link>
        ))}
      </div>
      <h2 className="mb-3 mt-10 text-base font-semibold">Đề thi gần đây</h2>
      <RecentExams />
    </section>
  );
}

function Message({ code, title, hint }: Readonly<{ code: string; title: string; hint: string }>) {
  const navigate = useNavigate();
  return (
    <section className="py-16 text-center">
      <p className="text-4xl font-semibold text-muted">{code}</p>
      <h1 className="mt-2 text-xl font-semibold">{title}</h1>
      <p className="mt-1 text-sm text-muted">{hint}</p>
      <div className="mt-6 flex justify-center gap-3">
        <Button onClick={() => navigate("/")}>Về trang chủ</Button>
        <Button variant="outline" onClick={() => navigate(-1)}>Quay lại</Button>
      </div>
    </section>
  );
}

export const NotFound = () => <Message code="404" title="Không tìm thấy trang" hint="Đường dẫn không tồn tại hoặc đã được chuyển." />;
export const Forbidden = () => <Message code="403" title="Không có quyền truy cập" hint="Trang này chỉ dành cho quản trị viên." />;

/** Role guard: wrap an element, e.g. guard(["admin"], <Page/>). Renders 403 for other roles. */
export function RequireRole({ roles, children }: Readonly<{ roles: UserRole[]; children: ReactNode }>) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/" replace />;
  return roles.includes(user.role) ? children : <Forbidden />;
}

export const guard = (roles: UserRole[], el: ReactNode) => <RequireRole roles={roles}>{el}</RequireRole>;
