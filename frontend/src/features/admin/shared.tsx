import { useCallback, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const LINKS = [
  { to: "/admin/sources", label: "Nguồn tài liệu" },
  { to: "/admin/bank", label: "Ngân hàng đề" },
  { to: "/admin/teachers", label: "Giáo viên" },
];

// Link row shared by the three admin pages; every target is a real route.
export function AdminNav() {
  return (
    <nav aria-label="Quản trị" className="mb-6 flex gap-4 border-b border-line">
      {LINKS.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            cn("border-b-2 pb-2 text-sm", isActive ? "border-accent text-ink" : "border-transparent text-muted")
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}

export const errText = (e: unknown) => (e instanceof Error ? e.message : "Đã xảy ra lỗi");

// Loads data once and on retry; `data === null && !error` means loading.
export function useLoad<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    setData(null);
    fn().then(setData, (e) => setError(errText(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(load, [load]);
  return { data, setData, error, reload: load };
}

export function Loading() {
  return <p role="status" className="py-8 text-sm text-muted">Đang tải…</p>;
}

export function Failed({ message, onRetry }: Readonly<{ message: string; onRetry: () => void }>) {
  return <ErrorState message={message} onRetry={onRetry} />;
}

export function ConfirmDialog({
  open, onOpenChange, title, body, confirmLabel, onConfirm,
}: Readonly<{
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
}>) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title}>
        <p className="text-sm text-muted">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Hủy</Button>
          </DialogClose>
          <Button variant="danger" onClick={() => { onOpenChange(false); onConfirm(); }}>{confirmLabel}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function Field({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <label className="mb-3 block text-sm">
      <span className="mb-1 block text-muted">{label}</span>
      {children}
    </label>
  );
}
