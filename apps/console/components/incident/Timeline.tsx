/**
 * The live execution timeline — the component the demo is for.
 *
 * Events arrive over the WebSocket and append here. `aria-live="polite"`
 * announces each new line, because an operator using a screen reader has to be
 * able to follow the loop too (DESIGN_SYSTEM.md §10).
 *
 * It renders only what the backend sends: a stage, a status, a message and a
 * timestamp. There is no model output here. The structured diagnosis has its
 * own card; raw generations are not on the wire at all.
 */

"use client";

import { useEffect, useRef } from "react";

import { Icon, type IconName } from "../ui/Icon";
import type { LoopEvent } from "@/lib/api";

const STATUS_ICON: Record<string, IconName> = {
  started: "pending",
  ok: "check",
  failed: "cross",
  info: "info",
};

const STATUS_COLOUR: Record<string, string> = {
  started: "var(--k-state-detected)",
  ok: "var(--k-risk-low)",
  failed: "var(--k-risk-high)",
  info: "var(--k-text-muted)",
};

const clock = (iso: string): string => {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : at.toLocaleTimeString("en-GB");
};

export function Timeline({
  events,
  connected,
}: {
  events: LoopEvent[];
  connected: boolean;
}) {
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);

  return (
    <section
      aria-labelledby="timeline-heading"
      style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--k-space-3)",
          marginBottom: "var(--k-space-3)",
        }}
      >
        <h2 id="timeline-heading">Execution timeline</h2>
        <span className="k-xs k-faint">
          {connected ? "Live · streaming" : "Reconnecting"} · {events.length}{" "}
          {events.length === 1 ? "event" : "events"}
        </span>
      </header>

      {events.length === 0 ? (
        <p className="k-sm k-muted" style={{ margin: 0 }}>
          No events yet. Start a loop run to watch detection, diagnosis,
          validation, repair and verification arrive here as they happen.
        </p>
      ) : (
        <ol
          className="k-scroll"
          aria-live="polite"
          aria-relevant="additions"
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            flex: 1,
            minHeight: 0,
          }}
        >
          {events.map((event) => (
            <li
              key={event.seq}
              style={{
                display: "grid",
                gridTemplateColumns: "76px 16px 1fr",
                gap: "var(--k-space-3)",
                alignItems: "start",
                padding: "7px 0",
                borderBottom: "1px solid var(--k-border-subtle)",
              }}
            >
              <time
                className="k-mono-sm k-faint"
                dateTime={event.at}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {clock(event.at)}
              </time>
              <span
                style={{
                  color: STATUS_COLOUR[event.status] ?? "var(--k-text-muted)",
                  display: "flex",
                  marginTop: 3,
                }}
              >
                <Icon name={STATUS_ICON[event.status] ?? "info"} />
              </span>
              <span>
                <span className="k-mono-sm" style={{ color: "var(--k-text-muted)" }}>
                  {event.stage}
                </span>{" "}
                <span className="k-sm">{event.message}</span>
                <span className="k-sr-only">
                  {" "}
                  Status: {event.status}.
                </span>
              </span>
            </li>
          ))}
          <li ref={end as never} aria-hidden="true" />
        </ol>
      )}
    </section>
  );
}
