import { useFetch } from "./useFetch";

interface SystemInfo {
  region: string;
  cluster: string;
  version: string;
  source: string;
  error: string | null;
  services: { name: string; status: string | null; running: number | null; desired: number | null; tag: string | null }[];
}

export function Footer({ lastEventId, eventCount }: { lastEventId: number; eventCount: number }) {
  const { data } = useFetch<SystemInfo>("/api/system", 60000);
  return (
    <footer className="foot">
      <span className="foot-item">
        <span className="foot-k">env</span> {data ? `${data.region} · ${data.cluster}` : "…"}
        {data?.source === "local" && <span className="foot-local">local</span>}
      </span>
      {(data?.services ?? []).map((s) => (
        <span key={s.name} className="foot-item">
          <span className={`dot dot-${s.status === "ACTIVE" || s.status === "local" ? "ok" : "dim"}`} />
          <span className="foot-k">{s.name}</span> <code>{s.tag ?? "—"}</code>
          {s.running != null && (
            <span className="muted">
              {" "}
              {s.running}/{s.desired}
            </span>
          )}
        </span>
      ))}
      <span className="foot-item foot-right">
        <span className="foot-k">events</span> {eventCount.toLocaleString()} <span className="muted">· last id</span> <code>{lastEventId}</code>
        <span className="muted"> · mission-control {data?.version ?? ""}</span>
      </span>
    </footer>
  );
}
