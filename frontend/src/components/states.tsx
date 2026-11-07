import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function EmptyState({ title, hint, children }: Readonly<{ title: string; hint?: string; children?: ReactNode }>) {
  return (
    <div className="border border-dashed border-line px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-muted">{hint}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: Readonly<{ message: string; onRetry?: () => void }>) {
  return (
    <div role="alert" className="border border-bad px-6 py-8 text-center">
      <p className="font-medium text-bad">{message}</p>
      {onRetry && (
        <Button variant="outline" className="mt-4" onClick={onRetry}>
          Thử lại
        </Button>
      )}
    </div>
  );
}

export function ComingSoon({ title }: Readonly<{ title: string }>) {
  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">{title}</h1>
      <EmptyState title="Màn hình này đang được xây dựng" hint="Sẽ có trong phiên bản tới.">
        <Link to="/" className="text-accent underline">Về trang chủ</Link>
      </EmptyState>
    </section>
  );
}
