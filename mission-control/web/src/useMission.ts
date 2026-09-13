import { useCallback, useEffect, useRef, useState } from "react";
import type { MissionEvent, MissionState } from "./types";

const MAX_EVENTS = 400;

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

export async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { detail?: string }).detail || `${r.status} ${url}`);
  return data as T;
}

export interface Mission {
  state: MissionState | null;
  stateAt: number; // Date.now() when `state` arrived, for live counters
  events: MissionEvent[];
  connected: boolean;
  transport: "ws" | "poll" | "none";
  replayFlash: boolean;
}

/** Connect to Mission Control: WebSocket first, polling when it fails, reconnect with backoff. */
export function useMission(): Mission {
  const [state, setState] = useState<MissionState | null>(null);
  const [stateAt, setStateAt] = useState<number>(Date.now());
  const [events, setEvents] = useState<MissionEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [transport, setTransport] = useState<Mission["transport"]>("none");
  const [replayFlash, setReplayFlash] = useState(false);
  const replayTimer = useRef<number | null>(null);
  const newestId = useRef(0);

  const applyState = useCallback((s: MissionState) => {
    setState(s);
    setStateAt(Date.now());
  }, []);

  const pushEvent = useCallback((e: MissionEvent) => {
    newestId.current = Math.max(newestId.current, e.id);
    setEvents((prev) => (prev.some((p) => p.id === e.id) ? prev : [e, ...prev].slice(0, MAX_EVENTS)));
    if (e.replay) {
      setReplayFlash(true);
      if (replayTimer.current) window.clearTimeout(replayTimer.current);
      replayTimer.current = window.setTimeout(() => setReplayFlash(false), 15000);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let backoff = 1000;
    let reconnectTimer: number | null = null;
    let pollTimer: number | null = null;

    const loadInitial = async () => {
      try {
        const [s, evs] = await Promise.all([
          getJSON<MissionState>("/api/state"),
          getJSON<MissionEvent[]>("/api/events?after=0&limit=2000"),
        ]);
        if (!alive) return;
        applyState(s);
        newestId.current = evs.length ? evs[evs.length - 1].id : 0;
        setEvents(evs.slice(-MAX_EVENTS).reverse());
      } catch {
        /* the poll loop below will keep trying */
      }
    };

    const startPolling = () => {
      if (pollTimer) return;
      setTransport("poll");
      pollTimer = window.setInterval(async () => {
        try {
          const s = await getJSON<MissionState>("/api/state");
          if (!alive) return;
          applyState(s);
          setConnected(true);
          const last = s.last_event_id;
          const newest = newestId.current;
          if (last > newest) {
            const evs = await getJSON<MissionEvent[]>(`/api/events?after=${newest}&limit=500`);
            if (alive) evs.forEach(pushEvent);
          }
        } catch {
          if (alive) setConnected(false);
        }
      }, 2000);
    };

    const stopPolling = () => {
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const connect = async () => {
      if (!alive) return;
      try {
        const { token } = await getJSON<{ token: string }>("/api/ws-token");
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${proto}//${location.host}/ws?token=${encodeURIComponent(token)}`);
      } catch {
        startPolling();
        scheduleReconnect();
        return;
      }
      ws.onopen = () => {
        if (!alive) return;
        backoff = 1000;
        stopPolling();
        setTransport("ws");
        setConnected(true);
      };
      ws.onmessage = (m) => {
        if (!alive) return;
        try {
          const msg = JSON.parse(m.data);
          if (msg.type === "state") applyState(msg as MissionState);
          else if (msg.type === "event") pushEvent(msg.event as MissionEvent);
          else if (msg.type === "queues")
            setState((prev) => (prev ? { ...prev, queues: msg.queues as Record<string, number> } : prev));
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (!alive) return;
        setConnected(false);
        startPolling();
        scheduleReconnect();
      };
      ws.onerror = () => ws?.close();
    };

    const scheduleReconnect = () => {
      if (reconnectTimer || !alive) return;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        backoff = Math.min(backoff * 2, 15000);
        void connect();
      }, backoff);
    };

    void loadInitial().then(connect);
    return () => {
      alive = false;
      stopPolling();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { state, stateAt, events, connected, transport, replayFlash };
}

/** A 1 Hz tick for live counters. */
export function useClock(ms = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}
