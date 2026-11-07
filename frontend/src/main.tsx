import "katex/dist/katex.min.css";
import "./styles/index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, useRoutes } from "react-router-dom";

import { routes } from "./app/routes";
import { AuthProvider, useAuth } from "./auth";
import Login from "./features/common/Login";
import { ErrorBoundary } from "./features/common/ErrorBoundary";

function App() {
  const { user, loading } = useAuth();
  const element = useRoutes(routes);
  if (loading) return <p className="p-8 text-center text-muted">Đang tải…</p>;
  if (!user) return <Login />;
  return element;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
);
