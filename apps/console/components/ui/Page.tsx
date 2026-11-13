/**
 * The frame every page but Operations shares: the rail, a title, one line on
 * what the page answers, and the scrolling content.
 *
 * `Section` and `Empty` moved here from the old observability page when it
 * was split into History, Logs, Metrics and Traces (ADR 0029), so the four
 * pages read as one product.
 */

import { Rail } from "./Rail";
import type { System } from "@/lib/api";

export function Page({
  system,
  current,
  title,
  intro,
  children,
}: {
  system: System | null;
  current: string;
  title: string;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail
        mode={system?.mode ?? "SIMULATION"}
        modeEnforced={system?.mode_is_enforced ?? false}
        current={current}
      />
      <main
        className="k-scroll"
        style={{ flex: 1, padding: "var(--k-space-5) var(--k-space-6)", minWidth: 0 }}
      >
        <header style={{ marginBottom: "var(--k-space-4)", maxWidth: 1040 }}>
          <h1>{title}</h1>
          <p className="k-sm k-muted" style={{ margin: "4px 0 0", maxWidth: "76ch" }}>
            {intro}
          </p>
        </header>
        {children}
      </main>
    </div>
  );
}

export function Section({
  title,
  hint,
  children,
  right,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: "var(--k-space-5)", maxWidth: 1040 }}>
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--k-space-3)",
          marginBottom: "var(--k-space-2)",
        }}
      >
        <h2 style={{ margin: 0 }}>{title}</h2>
        {right}
      </header>
      <p className="k-sm k-muted" style={{ margin: "0 0 var(--k-space-3)", maxWidth: "76ch" }}>
        {hint}
      </p>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="k-sm k-muted"
      style={{
        margin: 0,
        padding: "var(--k-space-3)",
        border: "1px dashed var(--k-border)",
        borderRadius: "var(--k-radius-sm)",
      }}
    >
      {children}
    </p>
  );
}

/** What failed and what fixes it (§8 Error), shown above the content. */
export function Unreachable({ message }: { message: string }) {
  if (!message) return null;
  return (
    <p className="k-sm" role="alert" style={{ color: "var(--k-state-escalated)" }}>
      {message}
    </p>
  );
}

export const UNREACHABLE =
  "Cannot reach the Kavach control plane. Start it with `make up`, and this page retries on its own.";
