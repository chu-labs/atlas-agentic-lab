import { useEffect, useRef, useState } from "react";

/** The board has no login; the browser acts as the product owner. */
export const ME = "maroun";

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-Actor": ME },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  get: <T>(url: string) => req<T>("GET", url),
  post: <T>(url: string, body: unknown) => req<T>("POST", url, body),
  patch: <T>(url: string, body: unknown) => req<T>("PATCH", url, body),
};

/** Poll a JSON endpoint every `ms`. Keeps the last good value across errors; `refresh` forces a tick. */
export function usePoll<T>(url: string | null, ms = 2000): { data: T | null; error: string | null; stale: boolean; refresh: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [nonce, setNonce] = useState(0);
  const inflight = useRef(false);

  useEffect(() => {
    if (!url) return;
    let alive = true;
    const tick = async () => {
      if (inflight.current) return;
      inflight.current = true;
      try {
        const d = await api.get<T>(url);
        if (alive) {
          setData(d);
          setError(null);
          setStale(false);
        }
      } catch (e) {
        if (alive) {
          setError((e as Error).message);
          setStale(true);
        }
      } finally {
        inflight.current = false;
      }
    };
    void tick();
    const id = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [url, ms, nonce]);

  useEffect(() => {
    setData(null);
    setError(null);
  }, [url]);

  return { data, error, stale, refresh: () => setNonce((n) => n + 1) };
}
