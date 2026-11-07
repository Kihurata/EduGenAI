import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "@/components/states";

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="mx-auto max-w-lg px-4 py-24">
        <h1 className="sr-only">Lỗi</h1>
        <ErrorState message="Đã có lỗi xảy ra. Hãy tải lại trang." onRetry={() => window.location.reload()} />
      </main>
    );
  }
}
