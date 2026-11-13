/**
 * Small, pure derivations for the Metrics and Traces pages.
 *
 * Nothing here is a new measurement: every figure comes from fields the API
 * already returns (incident timestamps and status, stored loop events).
 * Pure functions, so the arithmetic is tested without a browser.
 */

import type { IncidentSummary, LoopEvent } from "./api";
import { seconds } from "./ascii";

export type StageTiming = {
  stage: string;
  /** Seconds after the run's first event. */
  offsetS: number;
  /** First line of the stage to its last. 0 when it logged one line. */
  tookS: number;
  /** The stage's last status: ok, failed, info or started. */
  status: string;
};

const at = (e: LoopEvent): number => Date.parse(e.at);

/**
 * One row per stage of one run, in the order the stages began.
 *
 * A stage spans its first line to its last, so `repair`, which logs once
 * before the gate and once after it, includes the gate's time. That is what
 * the events say; it is not split further.
 */
export function stageTimings(events: LoopEvent[]): StageTiming[] {
  const sorted = [...events].filter((e) => Number.isFinite(at(e))).sort((a, b) => at(a) - at(b));
  if (sorted.length === 0) return [];
  const t0 = at(sorted[0]!);
  const first = new Map<string, LoopEvent>();
  const last = new Map<string, LoopEvent>();
  for (const e of sorted) {
    if (!first.has(e.stage)) first.set(e.stage, e);
    last.set(e.stage, e);
  }
  return [...first.entries()].map(([stage, start]) => {
    const end = last.get(stage)!;
    return {
      stage,
      offsetS: (at(start) - t0) / 1000,
      tookS: (at(end) - at(start)) / 1000,
      status: end.status,
    };
  });
}

/** Seconds from a run's first event to its last, or null with no events. */
export function runSeconds(events: LoopEvent[]): number | null {
  const times = events.map(at).filter(Number.isFinite);
  return times.length ? (Math.max(...times) - Math.min(...times)) / 1000 : null;
}

export type ClassRow = {
  faultClass: string;
  incidents: number;
  resolved: number;
  escalated: number;
  /** An approved heal is two rows: this parked plan and the run that fixed
   *  it (counted under `resolved`). Shown so the row adds up. */
  approved: number;
  /** Median over RESOLVED incidents only; null when none resolved. */
  medianMttrS: number | null;
};

export const median = (values: number[]): number | null => {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2;
};

/** Incidents per fault class, most frequent first. Rows with no class (no
 *  fault found, or no diagnosis) are grouped under "none". */
export function byFaultClass(incidents: IncidentSummary[]): ClassRow[] {
  const groups = new Map<string, IncidentSummary[]>();
  for (const i of incidents) {
    const key = i.fault_class ?? "none";
    groups.set(key, [...(groups.get(key) ?? []), i]);
  }
  return [...groups.entries()]
    .map(([faultClass, rows]) => ({
      faultClass,
      incidents: rows.length,
      resolved: rows.filter((r) => r.status === "RESOLVED").length,
      escalated: rows.filter((r) => r.status === "ESCALATED").length,
      approved: rows.filter((r) => r.status === "APPROVED").length,
      medianMttrS: median(
        rows
          .filter((r) => r.status === "RESOLVED")
          .map((r) => seconds(r.detected_at, r.resolved_at))
          .filter((s): s is number => s !== null),
      ),
    }))
    .sort((a, b) => b.incidents - a.incidents || a.faultClass.localeCompare(b.faultClass));
}
