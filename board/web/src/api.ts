import { useEffect, useRef, useState } from "react";

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

/** Poll a JSON endpoint every `ms` milliseconds. Keeps the last good value across errors. */
export function usePoll<T>(url: string, ms = 2000): { data: T | null; error: string | null; stale: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const inflight = useRef(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    const tick = async () => {
      if (inflight.current) return;
      inflight.current = true;
      try {
        const d = await getJSON<T>(url);
        if (alive) {
          setData(d);
          setError(null);
          setStale(false);
        }
      } catch (e) {
        if (alive) {
          setError(String(e));
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
  }, [url, ms]);

  return { data, error, stale };
}
