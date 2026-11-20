/**
 * Automatic checks (ADR 0032): a loop run every few minutes with nobody
 * clicking Run loop. Off by default, and a restart returns to the setting.
 *
 * It never starts while a plan waits for approval: each such run would park a
 * duplicate incident and spend a slot of the hourly limit the operator's own
 * Approve needs.
 */

"use client";

import { useState } from "react";

import { api, type AutoCheck, type Mode } from "@/lib/api";
import { usePolled } from "@/lib/live";

const load = () => api.GET("/v1/auto-check");

export function AutoCheckSwitch({ mode }: { mode: Mode }) {
  const { data, failed } = usePolled(load, 5_000);
  // The reply to a switch is shown until the next poll replaces it: the
  // poll is the truth, the reply is just newer for the next few seconds.
  const [fresh, setFresh] = useState<{ value: AutoCheck; over: AutoCheck | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState("");

  const state = fresh && fresh.over === data ? fresh.value : data;
  const minutes = Math.round((state?.every_s ?? 300) / 60);

  const flip = async (): Promise<void> => {
    if (!state) return;
    setBusy(true);
    setRefused("");
    try {
      const { data: next, error } = await api.PUT("/v1/auto-check", {
        body: { enabled: !state.enabled },
      });
      if (error || !next) {
        setRefused("The control plane refused the change.");
        return;
      }
      setFresh({ value: next, over: data });
    } catch {
      setRefused("Cannot reach the Kavach control plane.");
    } finally {
      setBusy(false);
    }
  };

  const on = state?.enabled ?? false;

  return (
    <section aria-labelledby="auto-check-heading" className="k-card">
      <h3 id="auto-check-heading">Automatic checks</h3>

      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-labelledby="auto-check-heading"
        disabled={busy || !state}
        onClick={() => void flip()}
        style={{
          marginTop: "var(--k-space-3)",
          width: "100%",
          minHeight: 40,
          borderRadius: "var(--k-radius-md)",
          border: "1px solid var(--k-border)",
          background: on ? "var(--k-surface-raised)" : "transparent",
          color: on ? "var(--k-text)" : "var(--k-text-muted)",
          fontWeight: on ? 600 : 400,
          fontSize: 12,
        }}
      >
        {on ? `On · every ${minutes} min` : "Off"}
      </button>

      <p className="k-xs k-muted" style={{ margin: "var(--k-space-2) 0 0" }}>
        {on
          ? `A check runs every ${minutes} minutes, and never while a plan waits for approval.`
          : `Switch on to run a check every ${minutes} minutes without clicking Run loop.`}
        {on && mode === "AUTONOMOUS" && " In Autonomous mode, a low-risk repair it finds runs without asking."}
      </p>

      {state?.last_result && (
        <p className="k-xs k-faint" style={{ margin: "4px 0 0" }}>
          Last: {state.last_result}
          {state.last_at ? ` at ${state.last_at.slice(11, 16)} UTC` : ""}
        </p>
      )}

      {(refused || (failed && !state)) && (
        <p role="alert" className="k-xs" style={{ margin: "4px 0 0", color: "var(--k-risk-high)" }}>
          {refused || "Cannot reach the Kavach control plane."}
        </p>
      )}
    </section>
  );
}
