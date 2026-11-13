/**
 * The arithmetic behind the Metrics and Traces pages.
 */

import { describe, expect, it } from "vitest";

import type { IncidentSummary, LoopEvent } from "@/lib/api";
import { byFaultClass, runSeconds, stageTimings } from "@/lib/stats";

const ev = (stage: string, status: string, at: string, seq = 1): LoopEvent => ({
  seq,
  at: `2026-11-13T05:44:${at}+00:00`,
  incident_id: "INC-1",
  stage,
  status,
  message: stage,
});

describe("stage timings", () => {
  const run = [
    ev("run", "started", "00.000"),
    ev("detect", "started", "01.000"),
    ev("detect", "ok", "13.000"),
    ev("repair", "started", "14.000"),
    ev("gate", "ok", "14.500"),
    ev("repair", "ok", "15.000"),
    ev("resolve", "ok", "32.000"),
  ];

  it("gives each stage its start, its length and how it ended, in order", () => {
    expect(stageTimings(run)).toEqual([
      { stage: "run", offsetS: 0, tookS: 0, status: "started" },
      { stage: "detect", offsetS: 1, tookS: 12, status: "ok" },
      { stage: "repair", offsetS: 14, tookS: 1, status: "ok" },
      { stage: "gate", offsetS: 14.5, tookS: 0, status: "ok" },
      { stage: "resolve", offsetS: 32, tookS: 0, status: "ok" },
    ]);
  });

  it("does not depend on the order the events arrive in", () => {
    expect(stageTimings([...run].reverse())).toEqual(stageTimings(run));
  });

  it("measures the run from its first line to its last", () => {
    expect(runSeconds(run)).toBe(32);
  });

  it("has nothing to say about a run with no stored events", () => {
    expect(stageTimings([])).toEqual([]);
    expect(runSeconds([])).toBeNull();
  });
});

const inc = (
  fault_class: string | null,
  status: string,
  took?: number,
): IncidentSummary => ({
  incident_id: `INC-${Math.random()}`,
  project: "simple-rag",
  status,
  detected_at: "2026-11-13T05:00:00+00:00",
  resolved_at:
    took === undefined ? "" : new Date(Date.parse("2026-11-13T05:00:00Z") + took * 1000).toISOString(),
  fault_class,
  fault_name: null,
  service: "backend",
  diagnosed_by: "llm_rca",
  outcome: "",
});

describe("per fault class", () => {
  it("counts, and takes the median MTTR over resolved incidents only", () => {
    const rows = byFaultClass([
      inc("F08", "RESOLVED", 40),
      inc("F08", "RESOLVED", 60),
      inc("F08", "RESOLVED", 50),
      inc("F08", "APPROVED"),
      inc("F07", "ESCALATED"),
      inc(null, "NO_FAULT"),
    ]);
    expect(rows[0]).toEqual({
      faultClass: "F08",
      incidents: 4,
      resolved: 3,
      escalated: 0,
      approved: 1,
      medianMttrS: 50,
    });
    expect(rows.find((r) => r.faultClass === "F07")).toMatchObject({
      escalated: 1,
      medianMttrS: null,
    });
    expect(rows.find((r) => r.faultClass === "none")?.incidents).toBe(1);
  });
});
