/**
 * The mode indicator — DESIGN_SYSTEM.md §7.9, and UX-01.
 *
 * It lives at the bottom of the 64px rail, so it is on every screen and never
 * scrolls away.
 *
 * IT IS AN INDICATOR, NOT A SWITCH, AND THAT IS DELIBERATE.
 * §7.9 describes a three-option segmented control. There is nothing to switch
 * to: `permit()` does not exist, the loop reads no mode, and the three modes
 * are P6 (docs/decisions/0006, amendment 2026-10-04). A control that appeared
 * to change a safety posture while changing nothing would be worse than no
 * control — so this reports the configured value and says, in words, that it is
 * configuration rather than an enforced gate.
 *
 * The segmented control arrives with the thing it controls.
 */

import { Icon } from "../ui/Icon";

export function ModeIndicator({
  mode,
  enforced,
}: {
  mode: string;
  enforced: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 4,
      }}
    >
      <span
        className="k-xs"
        title={
          enforced
            ? `Mode ${mode} is enforced by the safety engine.`
            : `Mode ${mode} is the configured default. It is not yet an enforced gate: the safety engine (permit()) is not implemented, and the loop runs only when an operator asks it to.`
        }
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 2,
          padding: "6px 2px",
          width: 58,
          textAlign: "center",
          borderRadius: "var(--k-radius-sm)",
          border: "1px solid var(--k-border)",
          background: "var(--k-surface-raised)",
          color: "var(--k-text-muted)",
        }}
      >
        <Icon name={enforced ? "shield" : "info"} />
        {/* The full word, never an abbreviation: UX-01 asks for the mode to be
            visible, and "Sim." on a projector is not that. 9px with tightened
            tracking fits the longest of the three ("Autonomous", 10 characters)
            inside a 64px rail. The earlier 10px/52px version clipped it. */}
        <span
          style={{
            fontSize: 9,
            lineHeight: "12px",
            letterSpacing: "-0.2px",
            whiteSpace: "nowrap",
          }}
        >
          {mode.charAt(0) + mode.slice(1).toLowerCase()}
        </span>
      </span>
      <span className="k-sr-only">
        Operating mode: {mode}.{" "}
        {enforced
          ? "Enforced by the safety engine."
          : "Configured value only; the safety engine is not implemented, so this does not gate any action."}
      </span>
      {!enforced && (
        <span
          aria-hidden="true"
          className="k-faint"
          style={{ fontSize: 9, lineHeight: "11px", textAlign: "center" }}
        >
          not gated
        </span>
      )}
    </div>
  );
}
