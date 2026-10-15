/**
 * Live data hooks.
 *
 * Two different problems, two different mechanisms, on purpose:
 *
 *   incident progress  WebSocket. Events are pushed the instant a loop stage
 *                      starts or finishes. The browser never polls for them.
 *   system health      a 5s interval. These are cheap independent probes with
 *                      no event source behind them; a socket would need the
 *                      backend to invent a change-detection tick to feed it.
 *
 * That split is the honest reading of "the browser must not poll aggressively
 * to simulate realtime": the thing that must be live is live, and a health
 * readout refreshing every five seconds is a readout, not a simulation.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type FleetMetrics,
  type Incident,
  type LoopEvent,
  type ModeState,
  type System,
  wsUrl,
} from "./api";

const HEALTH_INTERVAL_MS = 5000;
const RECONNECT_MS = 2000;

export function useSystem(): {
  system: System | null;
  error: string;
  refresh: () => void;
} {
  const [system, setSystem] = useState<System | null>(null);
  const [error, setError] = useState("");
  // `/v1/system` probes the target, Ollama and Prometheus, so it can take
  // longer than the poll interval. Without this guard the interval stacks
  // overlapping requests and the slowest response wins, which reads as the
  // health panel flickering between stale and fresh state.
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const { data, error: err } = await api.GET("/v1/system");
      if (err || !data) {
        setError(
          "Cannot reach the Kavach control plane. Start it with `make dev-api`.",
        );
        return;
      }
      setSystem(data);
      setError("");
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), HEALTH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [load]);

  return { system, error, refresh: () => void load() };
}

/**
 * Loop events over the WebSocket, de-duplicated by `seq`.
 *
 * The replay buffer the server sends on connect can overlap what is already
 * held, and a reconnect re-sends it, so `seq` is the identity. Without that a
 * dropped connection would duplicate the whole timeline.
 */
export function useEvents(): { events: LoopEvent[]; connected: boolean } {
  const [events, setEvents] = useState<LoopEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const seen = useRef<Set<number>>(new Set());

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = (): void => {
      if (closed) return;
      try {
        socket = new WebSocket(wsUrl());
      } catch {
        timer = setTimeout(connect, RECONNECT_MS);
        return;
      }
      socket.onopen = () => setConnected(true);
      socket.onmessage = (message: MessageEvent<string>) => {
        let event: LoopEvent;
        try {
          event = JSON.parse(message.data) as LoopEvent;
        } catch {
          return;
        }
        if (seen.current.has(event.seq)) return;
        seen.current.add(event.seq);
        setEvents((previous) => [...previous, event].sort((a, b) => a.seq - b.seq));
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) timer = setTimeout(connect, RECONNECT_MS);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, []);

  return { events, connected };
}

/** Incident list plus the selected incident's full detail. */
export function useIncidents(selectedId: string): {
  incidents: Incident[];
  selected: Incident | null;
  refresh: () => void;
} {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selected, setSelected] = useState<Incident | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET("/v1/incidents");
    if (data) setIncidents(data as Incident[]);
  }, []);

  const loadOne = useCallback(async (id: string) => {
    if (!id) {
      setSelected(null);
      return;
    }
    const { data } = await api.GET("/v1/incidents/{incident_id}", {
      params: { path: { incident_id: id } },
    });
    if (data) setSelected(data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadOne(selectedId);
  }, [selectedId, loadOne]);

  return {
    incidents,
    selected,
    refresh: () => {
      void load();
      void loadOne(selectedId);
    },
  };
}

/**
 * Operating mode and fleet metrics.
 *
 * Both are cheap and change rarely, so they load once and refresh when the
 * caller says something happened. Polling them would be noise.
 */
export function useSafetyState(): {
  mode: ModeState | null;
  metrics: FleetMetrics | null;
  setMode: (next: ModeState) => void;
  refresh: () => void;
} {
  const [mode, setModeState] = useState<ModeState | null>(null);
  const [metrics, setMetrics] = useState<FleetMetrics | null>(null);

  const load = useCallback(async () => {
    const [m, f] = await Promise.all([
      api.GET("/v1/mode"),
      api.GET("/v1/metrics"),
    ]);
    if (m.data) setModeState(m.data);
    if (f.data) setMetrics(f.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    mode,
    metrics,
    setMode: setModeState,
    refresh: () => void load(),
  };
}
