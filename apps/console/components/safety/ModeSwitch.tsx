/**
 * The mode switch — DESIGN_SYSTEM.md §7.9.
 *
 * P4 shipped an INDICATOR here and said so, because there was nothing to
 * switch: `permit()` did not exist and the loop read no mode. Both are now
 * true, so this is the segmented control the design always specified.
 *
 * `AUTONOMOUS` is the only segment filled with `--k-loop-gradient`, and
 * switching INTO it opens a confirmation listing exactly which actions become
 * auto-executable. Switching out is immediate and needs no confirmation —
 * moving toward caution never requires a dialog.
 *
 * The list in that confirmation is not decorative. An operator who cannot see
 * what they are enabling is being asked to consent to something they have not
 * been told, and `allowed_actions` is the one list that answers it.
 */

"use client";

import { useState } from "react";

import { Icon } from "../ui/Icon";
import { api, type Mode, type ModeState } from "@/lib/api";

const MODES: Mode[] = ["SIMULATION", "APPROVAL", "AUTONOMOUS"];

const BLURB: Record<Mode, string> = {
  SIMULATION: "Plans are produced and nothing is ever written.",
  APPROVAL: "Every repair waits for a human.",
  AUTONOMOUS: "Low-risk repairs run without asking.",
};

export function ModeSwitch({
  state,
  onChanged,
}: {
  state: ModeState | null;
  onChanged: (next: ModeState) => void;
}) {
  const [confirming, setConfirming] = useState<Mode | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");

  const current = state?.mode ?? "SIMULATION";

  const apply = async (mode: Mode): Promise<void> => {
    setBusy(true);
    setFailed("");
    const { data, error } = await api.PUT("/v1/mode", { body: { mode } });
    setBusy(false);
    setConfirming(null);
    if (error || !data) {
      setFailed("The control plane refused the mode change.");
      return;
    }
    onChanged(data);
  };

  const choose = (mode: Mode): void => {
    if (mode === current) return;
    // Only the step toward less caution asks.
    if (mode === "AUTONOMOUS") setConfirming(mode);
    else void apply(mode);
  };

  return (
    <section aria-labelledby="mode-heading" className="k-card">
      <h3 id="mode-heading">Operating mode</h3>

      <div
        role="radiogroup"
        aria-labelledby="mode-heading"
        style={{
          display: "flex",
          marginTop: "var(--k-space-3)",
          border: "1px solid var(--k-border)",
          borderRadius: "var(--k-radius-md)",
          overflow: "hidden",
        }}
      >
        {MODES.map((mode) => {
          const active = mode === current;
          const autonomous = mode === "AUTONOMOUS";
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={busy}
              onClick={() => choose(mode)}
              title={BLURB[mode]}
              style={{
                flex: 1,
                minHeight: 40,
                padding: "0 var(--k-space-2)",
                border: "none",
                borderRight: mode === "AUTONOMOUS" ? "none" : "1px solid var(--k-border)",
                background: active
                  ? autonomous
                    ? "var(--k-loop-gradient)"
                    : "var(--k-surface-raised)"
                  : "transparent",
                color: active
                  ? autonomous
                    ? "var(--k-text-inverse)"
                    : "var(--k-text)"
                  : "var(--k-text-muted)",
                fontWeight: active ? 600 : 400,
                fontSize: 12,
              }}
            >
              {mode.charAt(0) + mode.slice(1).toLowerCase()}
            </button>
          );
        })}
      </div>

      <p className="k-xs k-muted" style={{ margin: "var(--k-space-2) 0 0" }}>
        {BLURB[current]}
      </p>

      {state && (
        <dl
          className="k-mono-sm"
          style={{
            margin: "var(--k-space-3) 0 0",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "2px var(--k-space-2)",
          }}
        >
          <dt className="k-faint">enforced</dt>
          <dd style={{ margin: 0 }}>{state.enforced ? "yes" : "no"}</dd>
          <dt className="k-faint">allowed</dt>
          <dd style={{ margin: 0 }}>
            {state.allowed_actions.length > 0
              ? state.allowed_actions.join(", ")
              : "nothing — an empty allow-list denies everything"}
          </dd>
          {state.overridden && (
            <>
              <dt className="k-faint">manifest</dt>
              <dd style={{ margin: 0 }}>
                {state.manifest_mode}{" "}
                <span className="k-faint">(overridden for this process)</span>
              </dd>
            </>
          )}
        </dl>
      )}

      {failed && (
        <p role="alert" className="k-sm" style={{ color: "var(--k-risk-high)" }}>
          {failed}
        </p>
      )}

      {confirming && (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="confirm-heading"
          style={{
            marginTop: "var(--k-space-3)",
            padding: "var(--k-space-3)",
            borderRadius: "var(--k-radius-md)",
            border: "1px solid var(--k-risk-med)",
            background: "var(--k-risk-med-bg)",
          }}
        >
          <h4
            id="confirm-heading"
            className="k-sm"
            style={{ margin: 0, display: "flex", gap: 8, alignItems: "center",
                     color: "var(--k-risk-med)" }}
          >
            <Icon name="shield-alert" />
            Switch to autonomous?
          </h4>
          <p className="k-sm" style={{ margin: "var(--k-space-2) 0" }}>
            These actions become auto-executable without asking:
          </p>
          <ul className="k-mono-sm" style={{ margin: 0, paddingLeft: 18 }}>
            {(state?.allowed_actions ?? []).map((a) => (
              <li key={a}>{a}</li>
            ))}
            {(state?.allowed_actions ?? []).length === 0 && (
              <li className="k-muted">none — nothing would run anyway</li>
            )}
          </ul>
          <p className="k-xs k-muted" style={{ margin: "var(--k-space-2) 0 0" }}>
            Only low-risk actions run unattended. Medium goes to the sandbox,
            high and any model-authored patch still reach a human, and the
            deny-list is refused in every mode.
          </p>
          <div style={{ display: "flex", gap: "var(--k-space-2)", marginTop: "var(--k-space-3)" }}>
            <button
              type="button"
              disabled={busy}
              onClick={() => void apply(confirming)}
              style={{
                minHeight: 40, padding: "0 var(--k-space-4)",
                borderRadius: "var(--k-radius-md)", border: "none",
                background: "var(--k-loop-gradient)",
                color: "var(--k-text-inverse)", fontWeight: 600,
              }}
            >
              Enable autonomous
            </button>
            <button
              type="button"
              onClick={() => setConfirming(null)}
              style={{
                minHeight: 40, padding: "0 var(--k-space-4)",
                borderRadius: "var(--k-radius-md)",
                border: "1px solid var(--k-border-strong)",
                background: "transparent", color: "var(--k-text)",
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
