import { useCallback, useEffect, useRef, useState } from "react";

/** Poll a JSON endpoint; keeps the last good value across errors. `reload()` fetches immediately. */
export function useFetch<T>(url: string | null, ms = 15000): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inflight = useRef(false);
  const tick = useCallback(async () => {
    if (!url || inflight.current) return;
    inflight.current = true;
    setLoading(true);
    try {
      const r = await fetch(url, { headers: { Accept: "application/json" } });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error((body as { detail?: string }).detail || `${r.status}`);
      setData(body as T);
      setError(null);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      inflight.current = false;
      setLoading(false);
    }
  }, [url]);
  useEffect(() => {
    void tick();
    if (!url) return;
    const id = window.setInterval(() => void tick(), ms);
    return () => window.clearInterval(id);
  }, [tick, ms, url]);
  return { data, error, loading, reload: tick };
}
