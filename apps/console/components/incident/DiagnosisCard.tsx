/**
 * The RCA card — DESIGN_SYSTEM.md §7.5.
 *
 * Primary visual emphasis is on the fault class and the target service.
 * Confidence is rendered as a 5-segment bar, labelled as uncalibrated so the
 * operator is not misled into treating it as a calibrated probability.
 *
 * Validation checks are collapsed by default; the summary line shows the pass
 * count so an operator scanning the card knows whether there was any dispute.
 *
 * Stitch refinement:
 *   - Forensic Assessment badge & Midnight Operations surface treatment
 *   - Enhanced cited evidence chips and ruled-out alternatives disclosure
 *   - Preserves uncalibrated confidence text, aria-labels, and test contracts
 */

"use client";

import { useState } from "react";

import { Icon } from "../ui/Icon";
import { sentence } from "../ui/pills";
import type { Rca } from "@/lib/api";

const SEGMENTS = 5;

function ConfidenceBar({ value }: { value: number }) {
  const filled = Math.round(value * SEGMENTS);
  return (
    <span
      style={{ display: "inline-flex", gap: 3, alignItems: "center" }}
      role="img"
      aria-label={`Model-reported confidence ${value.toFixed(2)} of 1, uncalibrated`}
    >
      {Array.from({ length: SEGMENTS }, (_, index) => (
        <span
          key={index}
          style={{
            width: 18,
            height: 6,
            borderRadius: 2,
            background:
              index < filled
                ? "var(--k-confidence-fill)"
                : "var(--k-confidence-track)",
            boxShadow: index < filled ? "0 0 4px rgba(0, 229, 201, 0.4)" : "none",
          }}
        />
      ))}
    </span>
  );
}

export function DiagnosisCard({
  rca,
  onCitationClick,
}: {
  rca: Rca | null;
  onCitationClick: (eid: string) => void;
}) {
  const [showRuledOut, setShowRuledOut] = useState(false);
  const diagnosis = rca?.diagnosis ?? null;

  if (!rca) {
    return (
      <div className="k-card">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="activity" size={16} />
          Diagnosis
        </h3>
        <p className="k-sm k-muted" style={{ margin: "8px 0 0" }}>
          No diagnosis yet. The LLM RCA stage runs after deterministic detection
          finds a fault, and never before.
        </p>
      </div>
    );
  }

  if (!diagnosis) {
    const honest = /insufficient|unknown/i.test(rca.error ?? "");
    return (
      <div className="k-card">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="activity" size={16} />
          Diagnosis
        </h3>
        <p
          className="k-sm"
          style={{
            margin: "8px 0 0",
            color: honest ? "var(--k-text-muted)" : "var(--k-risk-high)",
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <Icon name={honest ? "info" : "cross"} />
          {honest
            ? "Not enough evidence to diagnose."
            : rca.error || "The diagnosis could not be read."}
        </p>
      </div>
    );
  }

  const approved = rca.approved;

  return (
    <div
      className="k-card"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--k-space-3)",
        boxShadow: "0 2px 12px rgba(0, 0, 0, 0.25)",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <span
              className="k-mono-sm"
              style={{
                padding: "2px 6px",
                borderRadius: "var(--k-radius-sm)",
                background: "var(--k-accent-glow)",
                color: "var(--k-accent)",
                fontSize: 10,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              FORENSIC ASSESSMENT
            </span>
          </div>
          <h3 style={{ display: "flex", alignItems: "baseline", gap: 8, margin: 0 }}>
            <span className="k-mono">{diagnosis.fault_class}</span>
            <span>{diagnosis.fault_name.replace(/_/g, " ")}</span>
          </h3>
          <p className="k-sm k-muted" style={{ margin: "4px 0 0" }}>
            on <span className="k-mono-sm">{diagnosis.service}</span> · diagnosed by{" "}
            <span className="k-mono-sm">{rca.model}</span> in {rca.latency_s}s
          </p>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 4,
            padding: "var(--k-space-1) var(--k-space-2)",
            background: "var(--k-surface-sunken)",
            borderRadius: "var(--k-radius-sm)",
            border: "1px solid var(--k-border-subtle)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "var(--k-space-2)" }}>
            <ConfidenceBar value={diagnosis.confidence} />
            <span className="k-mono" style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>
              {diagnosis.confidence.toFixed(2)}
            </span>
          </div>
          <span className="k-mono-sm k-faint" style={{ fontSize: 10 }}>
            RAW OUTPUT
          </span>
        </div>
      </div>

      <p
        className="k-xs"
        style={{
          margin: 0,
          padding: "var(--k-space-2) var(--k-space-3)",
          background: "var(--k-surface-sunken)",
          borderRadius: "var(--k-radius-sm)",
          border: "1px solid var(--k-border-subtle)",
          color: "var(--k-text-muted)",
          display: "flex",
          gap: 8,
          alignItems: "flex-start",
        }}
      >
        <span style={{ color: "var(--k-accent)", marginTop: 1 }}>
          <Icon name="info" size={14} />
        </span>
        <span>
          Uncalibrated. This is the model&apos;s own number, not a measured
          probability of correctness. The threshold it must clear is a floor, and
          the gate&apos;s real strength is the deterministic agreement check.
        </span>
      </p>

      <div>
        <h4 className="k-xs k-muted" style={{ margin: "0 0 6px", fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="activity" size={12} />
          Cited evidence
        </h4>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {diagnosis.evidence_ids.map((eid) => (
            <button
              key={eid}
              type="button"
              onClick={() => onCitationClick(eid)}
              className="k-mono-sm"
              style={{
                padding: "3px 8px",
                minHeight: 24,
                borderRadius: "var(--k-radius-sm)",
                border: "1px solid var(--k-border-strong)",
                background: "var(--k-surface-raised)",
                color: "var(--k-text)",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {eid}
            </button>
          ))}
        </div>
      </div>

      {diagnosis.reasoning && (
        <div
          style={{
            padding: "var(--k-space-2) var(--k-space-3)",
            background: "var(--k-surface-sunken)",
            borderRadius: "var(--k-radius-sm)",
            border: "1px solid var(--k-border-subtle)",
          }}
        >
          <p className="k-sm k-muted" style={{ margin: 0, lineHeight: 1.5 }}>
            {diagnosis.reasoning}
          </p>
        </div>
      )}

      <p
        className="k-sm"
        style={{
          margin: 0,
          display: "flex",
          gap: 8,
          alignItems: "center",
          color: approved ? "var(--k-risk-low)" : "var(--k-risk-high)",
          fontWeight: 500,
        }}
      >
        <Icon name={approved ? "check" : "cross"} />
        {approved
          ? `Validation accepted · approved action ${rca.approved_action}`
          : "Validation rejected this diagnosis · nothing was executed"}
      </p>

      {diagnosis.rejected_alternatives.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowRuledOut((open) => !open)}
            aria-expanded={showRuledOut}
            className="k-xs k-muted"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "none",
              border: "none",
              padding: "4px 0",
              minHeight: 24,
              cursor: "pointer",
            }}
          >
            <Icon name={showRuledOut ? "chevron-down" : "chevron-right"} />
            Ruled out ({diagnosis.rejected_alternatives.length})
          </button>
          {showRuledOut && (
            <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
              {diagnosis.rejected_alternatives.map((alt) => (
                <li
                  key={alt.fault_class}
                  className="k-sm k-muted"
                  style={{
                    padding: "var(--k-space-2) var(--k-space-3)",
                    background: "var(--k-surface-raised)",
                    borderRadius: "var(--k-radius-sm)",
                    border: "1px solid var(--k-border-subtle)",
                    display: "flex",
                    alignItems: "baseline",
                    gap: 8,
                  }}
                >
                  <span
                    className="k-mono-sm"
                    style={{
                      padding: "1px 6px",
                      borderRadius: "var(--k-radius-sm)",
                      background: "var(--k-risk-high-bg)",
                      color: "var(--k-risk-high)",
                      fontWeight: 700,
                      fontSize: 11,
                    }}
                  >
                    {alt.fault_class}
                  </span>
                  <span>— {alt.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {rca.validation && (
        <details>
          <summary className="k-xs k-muted" style={{ cursor: "pointer", minHeight: 24 }}>
            Validation checks ({rca.validation.checks.filter((c) => c.passed).length}/
            {rca.validation.checks.length} passed)
          </summary>
          <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none" }}>
            {rca.validation.checks.map((check) => (
              <li
                key={check.name}
                className="k-sm"
                style={{ display: "flex", gap: 8, alignItems: "start", padding: "3px 0" }}
              >
                <span
                  style={{
                    color: check.passed ? "var(--k-risk-low)" : "var(--k-risk-high)",
                    display: "flex",
                    marginTop: 3,
                  }}
                >
                  <Icon name={check.passed ? "check" : "cross"} />
                </span>
                <span>
                  <span className="k-mono-sm">{check.name}</span>{" "}
                  <span className="k-muted">{check.detail}</span>
                  <span className="k-sr-only">
                    {check.passed ? " passed" : " failed"}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {!approved && rca.validation?.rejection_reasons.length ? (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {rca.validation.rejection_reasons.map((reason) => (
            <li key={reason} className="k-sm" style={{ color: "var(--k-risk-high)" }}>
              {sentence(reason)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
