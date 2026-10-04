/**
 * The chip family: state pill, risk badge, probe pill, dependency status.
 *
 * One file because they are one pattern — icon plus text label in a tinted
 * `--k-radius-sm` chip — and four near-identical files would be four places to
 * forget the icon. The icon is not decoration: DESIGN_SYSTEM.md §10 forbids
 * colour-only state anywhere, so every one of these carries a glyph AND a word.
 */

import { Icon, type IconName } from "./Icon";
import { riskVars, stateVar } from "@/lib/tokens";

const CHIP: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "2px 10px",
  borderRadius: "var(--k-radius-sm)",
  fontSize: 12,
  lineHeight: "18px",
  fontWeight: 500,
  whiteSpace: "nowrap",
};

/** Sentence case, as §3.2 requires: "Resolved", never "RESOLVED". */
export const sentence = (value: string): string => {
  const words = value.replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

const STATE_ICON: Record<string, IconName> = {
  DETECTED: "info",
  NO_FAULT: "check",
  HEALING: "activity",
  RESOLVED: "check",
  ESCALATED: "cross",
};

export function StatePill({ status }: { status: string }) {
  const colour = stateVar(status);
  return (
    <span
      style={{
        ...CHIP,
        color: colour,
        background: "var(--k-surface-raised)",
        border: `1px solid ${colour}`,
      }}
    >
      <Icon name={STATE_ICON[status] ?? "info"} />
      {sentence(status)}
    </span>
  );
}

const RISK_ICON: Record<string, IconName> = {
  LOW: "shield",
  MEDIUM: "shield-alert",
  HIGH: "shield-x",
  DENIED: "ban",
};

export function RiskBadge({ tier }: { tier: string }) {
  const key = tier.toUpperCase();
  const { fg, bg } = riskVars(key);
  return (
    <span
      style={{
        ...CHIP,
        color: fg,
        background: bg,
        // 1px border in the tier colour at 30% alpha (§7.2).
        border: `1px solid color-mix(in srgb, ${fg} 30%, transparent)`,
      }}
    >
      <Icon name={RISK_ICON[key] ?? "ban"} />
      {sentence(key)}
    </span>
  );
}

/**
 * A verification probe. `pending` renders a hollow circle and must be visibly
 * present before it runs, so a missing probe is obvious (§7.8).
 */
export function ProbePill({
  label,
  state,
  detail,
}: {
  label: string;
  state: "pending" | "passed" | "failed";
  detail?: string;
}) {
  const colour =
    state === "passed"
      ? "var(--k-risk-low)"
      : state === "failed"
        ? "var(--k-risk-high)"
        : "var(--k-text-faint)";
  const icon: IconName =
    state === "passed" ? "check" : state === "failed" ? "cross" : "pending";
  return (
    <span
      style={{
        ...CHIP,
        color: colour,
        background: "var(--k-surface-raised)",
        border: `1px solid ${state === "pending" ? "var(--k-border)" : colour}`,
      }}
      title={detail}
    >
      <Icon name={icon} />
      {label}
      <span className="k-faint" style={{ fontWeight: 400 }}>
        {state === "pending" ? "pending" : state}
      </span>
    </span>
  );
}

/** Inline ok/not-ok with the word spelled out. Used in the health zone. */
export function OkText({ ok, okWord = "ok", badWord = "failing" }: {
  ok: boolean;
  okWord?: string;
  badWord?: string;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        color: ok ? "var(--k-risk-low)" : "var(--k-risk-high)",
      }}
    >
      <Icon name={ok ? "check" : "cross"} />
      {ok ? okWord : badWord}
    </span>
  );
}
