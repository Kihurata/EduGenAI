import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/api";
import { useAction } from "@/common";

function message(error: unknown): string {
  if (error instanceof ApiError) return error.messages.join(" ");
  return "Không đăng nhập được. Kiểm tra kết nối rồi thử lại.";
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  function submit(e: FormEvent) {
    e.preventDefault();
    // Login renders at whatever URL the previous user left (e.g. /admin/teachers): always land on home.
    void run(async () => {
      await login(email, password);
      navigate("/", { replace: true });
    });
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4 font-sans text-ink">
      <form onSubmit={submit} className="w-full max-w-sm border border-line bg-surface p-8">
        <div className="mb-6">
          <h1 className="text-xl font-semibold">EduGen</h1>
          <p className="text-sm text-muted">Sinh và chấm đề thi THPT</p>
        </div>
        <label className="mb-4 block text-sm font-medium">
          Email
          <Input className="mt-1" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        </label>
        <label className="mb-4 block text-sm font-medium">
          Mật khẩu
          <Input className="mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error != null && (
          <p role="alert" className="mb-4 text-sm text-bad">
            {message(error)}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Đang đăng nhập…" : "Đăng nhập"}
        </Button>
      </form>
    </main>
  );
}
