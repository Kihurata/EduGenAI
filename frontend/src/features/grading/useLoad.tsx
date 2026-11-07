import { useCallback, useEffect, useState } from "react";

import { ErrorState } from "@/components/states";

/** Loads async data; optional silent polling. `fn` must be stable per `deps`. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(fn, deps);
  const reload = useCallback(() => {
    setLoading(true);
    setError(false);
    load().then(setData, () => setError(true)).finally(() => setLoading(false));
  }, [load]);
  useEffect(reload, [reload]);
  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(() => load().then(setData, () => undefined), pollMs);
    return () => clearInterval(t);
  }, [load, pollMs]);
  return { data, error, loading, reload };
}

export const Loading = () => <p className="text-sm text-muted">Đang tải…</p>;

/** Standard loading / error gate; renders nothing when data is ready. */
export function Gate({ loading, error, reload, hasData }: Readonly<{ loading: boolean; error: boolean; reload: () => void; hasData: boolean }>) {
  if (error) return <ErrorState message="Không tải được dữ liệu." onRetry={reload} />;
  if (loading && !hasData) return <Loading />;
  return null;
}
