import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { navFor } from "@/app/nav";
import { MotifBackdrop } from "@/components/MotifBackdrop";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth";
import { cn } from "@/lib/utils";

export function AppShell() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  if (!user) return null;
  return (
    <div className="app">
      <MotifBackdrop />
      <header className="relative z-10 flex flex-wrap items-center gap-6 border-b border-line bg-surface px-6 py-3">
        <NavLink to="/" className="text-lg font-semibold text-accent">EduGen</NavLink>
        <nav className="flex flex-1 flex-wrap gap-4 text-sm" aria-label="Chính">
          {navFor(user.role).map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => cn("pb-0.5", isActive ? "border-b-2 border-accent font-medium text-ink" : "text-muted")}>
              {n.label}
              {n.prototype && <span className="ml-1 border border-line px-1 text-[10px] font-normal text-muted">Bản mẫu</span>}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3 text-sm text-muted">
          <span>{user.full_name} · {user.role === "admin" ? "Quản trị" : "Giáo viên"}</span>
          <Button variant="outline" onClick={() => void logout()}>Đăng xuất</Button>
        </div>
      </header>
      <main className="relative z-10 mx-auto max-w-6xl px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
