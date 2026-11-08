import { useState } from "react";

import { api } from "@/api";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, Td, Th } from "@/components/ui/table";
import type { User } from "@/types";
import { ConfirmDialog, errText, Failed, Field, Loading, useLoad } from "./shared";

export default function TeachersPage() {
  // API: GET /api/v1/admin/teachers
  const { data, setData, error, reload } = useLoad(() => api<User[]>("/admin/teachers"));
  const [actionError, setActionError] = useState<string | null>(null);
  const [locking, setLocking] = useState<User | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const shown = data?.filter((t) => !needle || t.full_name.toLowerCase().includes(needle) || t.email.toLowerCase().includes(needle));
  const active = data?.filter((t) => t.is_active).length ?? 0;

  // API: PATCH /api/v1/admin/teachers/{id} { is_active?, password? }
  async function patch(t: User, json: { is_active?: boolean; password?: string }) {
    setActionError(null);
    try {
      const u = await api<User>(`/admin/teachers/${t.id}`, { method: "PATCH", json });
      setData((p) => p?.map((x) => (x.id === u.id ? u : x)) ?? null);
    } catch (e) {
      setActionError(errText(e));
    }
  }

  return (
    <section>
      <div className="mb-1 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tài khoản giáo viên</h1>
        <AddTeacher onAdded={(u) => setData((p) => [...(p ?? []), u])} />
      </div>
      <p className="mb-4 text-sm text-muted">
        {data ? `${data.length} tài khoản · ${active} đang hoạt động · ${data.length - active} đã khóa` : "Quản lý tài khoản giáo viên của trường."}
      </p>
      {data && data.length > 0 && (
        <Input
          className="mb-4 max-w-xs"
          type="search"
          placeholder="Tìm theo họ tên, email"
          aria-label="Tìm theo họ tên, email"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      )}
      {actionError && (
        <p role="alert" className="mb-3 text-sm text-bad">
          {actionError}
        </p>
      )}
      {error && <Failed message={error} onRetry={reload} />}
      {!error && !data && <Loading />}
      {data?.length === 0 && <EmptyState title="Chưa có giáo viên" hint="Bấm “Thêm giáo viên” để tạo tài khoản đầu tiên." />}
      {data && data.length > 0 && shown?.length === 0 && <EmptyState title="Không có giáo viên phù hợp" hint="Thử từ khóa khác." />}
      {shown && shown.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>Họ tên</Th>
              <Th>Email</Th>
              <Th>Trạng thái</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.id}>
                <Td>{t.full_name}</Td>
                <Td className="text-muted">{t.email}</Td>
                <Td>
                  <Chip tone={t.is_active ? "ok" : "bad"}>{t.is_active ? "Hoạt động" : "Đã khóa"}</Chip>
                </Td>
                <Td className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => setResetting(t)}>
                      Đặt lại mật khẩu
                    </Button>
                    {t.is_active ? (
                      <Button variant="ghost" className="text-son" onClick={() => setLocking(t)}>
                        Khóa
                      </Button>
                    ) : (
                      <Button variant="outline" onClick={() => patch(t, { is_active: true })}>
                        Mở khóa
                      </Button>
                    )}
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <ConfirmDialog
        open={!!locking}
        onOpenChange={(o) => !o && setLocking(null)}
        title="Khóa tài khoản?"
        body={`${locking?.full_name ?? ""} sẽ bị đăng xuất khỏi mọi phiên và không đăng nhập được cho đến khi mở khóa.`}
        confirmLabel="Khóa"
        onConfirm={() => locking && patch(locking, { is_active: false })}
      />
      <ResetDialog target={resetting} onClose={() => setResetting(null)} onSubmit={(t, password) => patch(t, { password })} />
    </section>
  );
}

function ResetDialog({
  target,
  onClose,
  onSubmit,
}: Readonly<{ target: User | null; onClose: () => void; onSubmit: (t: User, p: string) => void }>) {
  const [pw, setPw] = useState("");
  const close = () => {
    onClose();
    setPw("");
  };
  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && close()}>
      <DialogContent title={`Đặt lại mật khẩu cho ${target?.full_name ?? ""}`}>
        <Field label="Mật khẩu mới (tối thiểu 8 ký tự)">
          <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
        </Field>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Hủy</Button>
          </DialogClose>
          <Button
            disabled={pw.length < 8}
            onClick={() => {
              if (target) onSubmit(target, pw);
              close();
            }}
          >
            Lưu
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function AddTeacher({ onAdded }: Readonly<{ onAdded: (u: User) => void }>) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ full_name: "", email: "", password: "" });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  async function submit() {
    setErr(null);
    try {
      // API: POST /api/v1/admin/teachers { email, password, full_name }
      onAdded(await api<User>("/admin/teachers", { method: "POST", json: f }));
      setOpen(false);
      setF({ full_name: "", email: "", password: "" });
    } catch (e) {
      setErr(errText(e));
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}>Thêm giáo viên</Button>
      <DialogContent title="Thêm giáo viên">
        <Field label="Họ tên">
          <Input value={f.full_name} onChange={set("full_name")} />
        </Field>
        <Field label="Email">
          <Input type="email" value={f.email} onChange={set("email")} />
        </Field>
        <Field label="Mật khẩu (tối thiểu 8 ký tự)">
          <Input type="password" value={f.password} onChange={set("password")} />
        </Field>
        {err && (
          <p role="alert" className="text-sm text-bad">
            {err}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Hủy</Button>
          </DialogClose>
          <Button disabled={!f.full_name.trim() || !f.email.trim() || f.password.length < 8} onClick={submit}>
            Tạo
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
