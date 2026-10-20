/**
 * Regression and accessibility tests for the LoopStageBar pipeline component.
 *
 * Requirements covered:
 * 1. Rendering the 7 canonical stages in the exact order:
 *    Detect → Collect → Diagnose → Gate → Execute → Verify → Resolved
 * 2. Completed, active/in_flight, failed, and pending state representations.
 * 3. Gate regression: successful gate marks Gate as Passed.
 * 4. Gate regression: denied or failed gate marks Gate as Failed, never Passed.
 * 5. Rollback events: distinct unwind banner without improperly illuminating Execute or Resolved.
 * 6. Empty / unknown / loading state behavior.
 * 7. Accessibility semantics: landmarks, aria-current="step", accessible stage labels, sr-only descriptions.
 * 8. Waiting for approval: reflects awaiting authorization state.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  calculatePipelineStages,
  LoopStageBar,
  PIPELINE_STAGES,
} from "@/components/incident/LoopStageBar";
import type { Incident, IncidentSummary, LoopEvent } from "@/lib/api";

import * as fx from "./fixtures";

describe("LoopStageBar pipeline component", () => {
  it("defines the 7 canonical stages in strict forward sequence", () => {
    const stageIds = PIPELINE_STAGES.map((s) => s.id);
    expect(stageIds).toEqual([
      "detect",
      "collect",
      "diagnose",
      "gate",
      "execute",
      "verify",
      "resolved",
    ]);

    const stageLabels = PIPELINE_STAGES.map((s) => s.label);
    expect(stageLabels).toEqual([
      "Detect",
      "Collect",
      "Diagnose",
      "Gate",
      "Execute",
      "Verify",
      "Resolved",
    ]);
  });

  it("renders all seven stages in correct order within the pipeline navigation", () => {
    render(<LoopStageBar events={[]} incident={null} />);

    const nav = screen.getByRole("navigation", { name: "Incident healing pipeline" });
    expect(nav).toBeInTheDocument();

    const list = within(nav).getByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(7);

    const expectedLabels = [
      "Detect",
      "Collect",
      "Diagnose",
      "Gate",
      "Execute",
      "Verify",
      "Resolved",
    ];

    items.forEach((item, index) => {
      const label = expectedLabels[index] ?? "";
      expect(within(item).getByText(label)).toBeInTheDocument();
    });
  });

  it("renders an empty/loading state with all stages pending and 0 reached", () => {
    render(<LoopStageBar events={[]} incident={null} />);

    expect(screen.getByText("0 of 7 stages reached")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    items.forEach((item) => {
      expect(within(item).getByText("Pending")).toBeInTheDocument();
      expect(item).not.toHaveAttribute("aria-current");
    });
  });

  it("correctly identifies completed, in-flight, failed, and pending stages", () => {
    const events: LoopEvent[] = [
      {
        seq: 1,
        at: "2026-10-04T10:00:00Z",
        incident_id: "INC-1",
        stage: "detect",
        status: "ok",
        message: "metric anomaly found",
      },
      {
        seq: 2,
        at: "2026-10-04T10:00:05Z",
        incident_id: "INC-1",
        stage: "evidence",
        status: "ok",
        message: "evidence items collected",
      },
      {
        seq: 3,
        at: "2026-10-04T10:00:10Z",
        incident_id: "INC-1",
        stage: "diagnose",
        status: "started",
        message: "rca model evaluating",
      },
    ];

    render(<LoopStageBar events={events} incidentId="INC-1" busy={true} />);

    expect(screen.getByText("2 of 7 stages reached")).toBeInTheDocument();

    const detectItem = screen.getByRole("listitem", { name: /^1\. Detect: Passed/ });
    expect(within(detectItem).getByText("Passed")).toBeInTheDocument();

    const collectItem = screen.getByRole("listitem", { name: /^2\. Collect: Passed/ });
    expect(within(collectItem).getByText("Passed")).toBeInTheDocument();

    const diagnoseItem = screen.getByRole("listitem", { name: /^3\. Diagnose: Running/ });
    expect(within(diagnoseItem).getByText("Running")).toBeInTheDocument();
    expect(diagnoseItem).toHaveAttribute("aria-current", "step");

    const gateItem = screen.getByRole("listitem", { name: /^4\. Gate: Pending/ });
    expect(within(gateItem).getByText("Pending")).toBeInTheDocument();
  });

  it("marks the gate stage as Passed upon a successful gate event", () => {
    const events: LoopEvent[] = [
      {
        seq: 1,
        at: "2026-10-04T10:00:00Z",
        incident_id: "INC-1",
        stage: "detect",
        status: "ok",
        message: "detected",
      },
      {
        seq: 2,
        at: "2026-10-04T10:00:05Z",
        incident_id: "INC-1",
        stage: "gate",
        status: "ok",
        message: "permit ALLOWED: restart target",
      },
    ];

    render(<LoopStageBar events={events} incidentId="INC-1" />);

    const gateItem = screen.getByRole("listitem", { name: /^4\. Gate: Passed/ });
    expect(within(gateItem).getByText("Passed")).toBeInTheDocument();
  });

  it("marks the gate stage as Failed upon a denied or failed gate event", () => {
    const events: LoopEvent[] = [
      {
        seq: 1,
        at: "2026-10-04T10:00:00Z",
        incident_id: "INC-1",
        stage: "detect",
        status: "ok",
        message: "detected",
      },
      {
        seq: 2,
        at: "2026-10-04T10:00:05Z",
        incident_id: "INC-1",
        stage: "gate",
        status: "failed",
        message: "permit DENIED: policy forbids destructive actions",
      },
    ];

    render(<LoopStageBar events={events} incidentId="INC-1" />);

    const gateItem = screen.getByRole("listitem", { name: /^4\. Gate: Failed/ });
    expect(within(gateItem).getByText("Failed")).toBeInTheDocument();
    expect(within(gateItem).queryByText("Passed")).not.toBeInTheDocument();
  });

  it("marks gate as Failed when preflight validation fails", () => {
    const events: LoopEvent[] = [
      {
        seq: 1,
        at: "2026-10-04T10:00:00Z",
        incident_id: "INC-1",
        stage: "detect",
        status: "ok",
        message: "detected",
      },
      {
        seq: 2,
        at: "2026-10-04T10:00:05Z",
        incident_id: "INC-1",
        stage: "validate",
        status: "failed",
        message: "preflight contract check failed",
      },
    ];

    render(<LoopStageBar events={events} incidentId="INC-1" />);

    const gateItem = screen.getByRole("listitem", { name: /^4\. Gate: Failed/ });
    expect(within(gateItem).getByText("Failed")).toBeInTheDocument();
  });

  it("handles rollback events via a dedicated status banner without falsely marking execute or resolved as passed", () => {
    const events: LoopEvent[] = [
      {
        seq: 1,
        at: "2026-10-04T10:00:00Z",
        incident_id: "INC-1",
        stage: "detect",
        status: "ok",
        message: "detected",
      },
      {
        seq: 2,
        at: "2026-10-04T10:00:05Z",
        incident_id: "INC-1",
        stage: "gate",
        status: "ok",
        message: "permit ALLOWED",
      },
      {
        seq: 3,
        at: "2026-10-04T10:00:10Z",
        incident_id: "INC-1",
        stage: "repair",
        status: "ok",
        message: "applied config patch",
      },
      {
        seq: 4,
        at: "2026-10-04T10:00:15Z",
        incident_id: "INC-1",
        stage: "verify",
        status: "failed",
        message: "golden quality probe failed",
      },
      {
        seq: 5,
        at: "2026-10-04T10:00:20Z",
        incident_id: "INC-1",
        stage: "rollback",
        status: "ok",
        message: "unwound 1/1 action, verified against pre-state witness",
      },
    ];

    const incident: IncidentSummary = {
      ...fx.summaries[0]!,
      incident_id: "INC-1",
      status: "ROLLED_BACK",
      outcome: "Quality probe failed; unwound cleanly",
    };

    render(<LoopStageBar events={events} incidentId="INC-1" incident={incident} />);

    // Rollback banner must be present
    const rollbackBanner = screen.getByRole("status", { name: "Rollback event" });
    expect(rollbackBanner).toBeInTheDocument();
    expect(within(rollbackBanner).getByText(/Rollback rolled back/i)).toBeInTheDocument();
    expect(within(rollbackBanner).getByText("Unwind")).toBeInTheDocument();
    expect(within(rollbackBanner).getByText(/unwound 1\/1 action/i)).toBeInTheDocument();

    // Verify stage must be Failed
    const verifyItem = screen.getByRole("listitem", { name: /^6\. Verify: Failed/ });
    expect(within(verifyItem).getByText("Failed")).toBeInTheDocument();

    // Resolved stage must NOT be passed just because rollback completed
    const resolvedItem = screen.getByRole("listitem", { name: /^7\. Resolved:/ });
    expect(within(resolvedItem).queryByText("Passed")).not.toBeInTheDocument();
  });

  it("represents an in-flight rollback state distinctly", () => {
    const events: LoopEvent[] = [
      {
        seq: 1,
        at: "2026-10-04T10:00:00Z",
        incident_id: "INC-1",
        stage: "verify",
        status: "failed",
        message: "probe failed",
      },
      {
        seq: 2,
        at: "2026-10-04T10:00:05Z",
        incident_id: "INC-1",
        stage: "rollback",
        status: "started",
        message: "unwinding 2 actions from undo stack",
      },
    ];

    render(<LoopStageBar events={events} incidentId="INC-1" busy={true} />);

    const rollbackBanner = screen.getByRole("status", { name: "Rollback event" });
    expect(within(rollbackBanner).getByText(/Rollback active/i)).toBeInTheDocument();
    expect(within(rollbackBanner).getByText(/unwinding 2 actions/i)).toBeInTheDocument();
  });

  it("marks gate as Awaiting approval when incident requires operator authorization", () => {
    const incident: Incident = {
      ...fx.resolvedIncident,
      incident_id: "INC-42",
      status: "AWAITING_APPROVAL",
      awaiting_approval: true,
    };

    render(<LoopStageBar events={[]} incidentId="INC-42" incident={incident} />);

    const gateItem = screen.getByRole("listitem", { name: /^4\. Gate: Awaiting approval/ });
    expect(within(gateItem).getByText("Awaiting approval")).toBeInTheDocument();
  });

  it("handles incidents with NO_FAULT outcome truthfully", () => {
    const incident: IncidentSummary = {
      ...fx.summaries[0]!,
      incident_id: "INC-NF",
      status: "NO_FAULT",
      outcome: "No fault detected",
    };

    render(<LoopStageBar events={[]} incidentId="INC-NF" incident={incident} />);

    const detectItem = screen.getByRole("listitem", { name: /^1\. Detect: Passed/ });
    expect(within(detectItem).getByText("Passed")).toBeInTheDocument();

    const resolvedItem = screen.getByRole("listitem", { name: /^7\. Resolved: Passed/ });
    expect(within(resolvedItem).getByText("Passed")).toBeInTheDocument();

    // Intermediate repair/gate stages never ran, so they remain Pending
    const executeItem = screen.getByRole("listitem", { name: /^5\. Execute: Pending/ });
    expect(within(executeItem).getByText("Pending")).toBeInTheDocument();
  });

  it("provides screen-reader accessible descriptions for every stage", () => {
    render(<LoopStageBar events={[]} incident={null} />);

    const srOnlyTexts = screen.getAllByText(/\. Status: Pending\./);
    expect(srOnlyTexts).toHaveLength(7);
  });

  it("filters events scoped to the selected incident id", () => {
    const events: LoopEvent[] = [
      {
        seq: 1,
        at: "2026-10-04T10:00:00Z",
        incident_id: "OTHER-INCIDENT",
        stage: "detect",
        status: "ok",
        message: "other incident",
      },
    ];

    const result = calculatePipelineStages(events, "CURRENT-INCIDENT", null, false);
    const detectStage = result.stages.find((s) => s.id === "detect");
    expect(detectStage?.status).toBe("pending");
  });
});
