/**
 * Tests for the Observability screen and dashboard telemetry integrations.
 *
 * Verifies:
 * - Telemetry summary tiles in the AI calls section (latency trend, tokens, validator rate).
 * - Interactive filtering of AI calls by model and verdict.
 * - Honest representations when telemetry data or metrics are unavailable.
 * - Alerts, exceptions, and logs presentation with severity chips and counts.
 * - VerificationStrip probe latency distribution and duration budget visualizations.
 * - SystemHealth fleet metric meters and healthy dependency ratios.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ObservabilityPage from "@/app/observability/page";
import { SystemHealth } from "@/components/safety/SystemHealth";
import { VerificationStrip } from "@/components/incident/VerificationStrip";
import type { Alert, LlmCall, LogLine } from "@/lib/api";

import * as fx from "./fixtures";

// Mock api client for ObservabilityPage
const sampleAlerts: Alert[] = [
  {
    id: "alert-1",
    severity: "warning",
    title: "High recovery duration threshold approached",
    detail: "Fast quality evaluation exceeded 80% of configured 5.0s budget.",
    action: "permit refused for concurrent runs",
  },
];

const sampleCalls: LlmCall[] = [
  {
    incident_id: "INC-101",
    model: "llama3:8b",
    latency_s: 1.4,
    prompt_tokens: 350,
    completion_tokens: 120,
    fault_class: "F06",
    confidence: 0.85,
    confidence_is_calibrated: false,
    approved: true,
    approved_action: "rollback_config",
    at: "2026-10-04T10:45:30Z",
    provider: "ollama",
    error: "",
  },
  {
    incident_id: "INC-102",
    model: "llama3:8b",
    latency_s: 2.2,
    prompt_tokens: 420,
    completion_tokens: 160,
    fault_class: "F08",
    confidence: 0.65,
    confidence_is_calibrated: false,
    approved: false,
    rejection_reasons: ["confidence 0.65 below required 0.75 threshold"],
    at: "2026-10-04T10:50:10Z",
    provider: "ollama",
    error: "",
  },
  {
    incident_id: "INC-103",
    model: "mistral:7b",
    latency_s: 1.1,
    prompt_tokens: 280,
    completion_tokens: 90,
    fault_class: "F01",
    confidence: 0.92,
    confidence_is_calibrated: false,
    approved: true,
    approved_action: "restart_container",
    at: "2026-10-04T10:55:00Z",
    provider: "ollama",
    error: "",
  },
];

const sampleLogs: LogLine[] = [
  {
    at: "2026-10-04T10:50:00.000Z",
    level: "warning",
    event: "permit_gate_refusal",
    detail: "confidence below threshold",
    incident_id: "INC-102",
    exception: "",
    logger: "kavach.gate",
  },
  {
    at: "2026-10-04T10:45:00.000Z",
    level: "info",
    event: "detection_scan_passed",
    detail: "no anomalies in 60s window",
    incident_id: "",
    exception: "",
    logger: "kavach.loop",
  },
];

vi.mock("@/lib/live", () => ({
  useSystem: () => ({
    system: fx.system,
    error: "",
    refresh: vi.fn(),
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      GET: vi.fn((path: string) => {
        if (path === "/v1/alerts") return Promise.resolve({ data: sampleAlerts });
        if (path === "/v1/llm-calls") return Promise.resolve({ data: sampleCalls });
        if (path === "/v1/logs") return Promise.resolve({ data: sampleLogs });
        return Promise.resolve({ data: null });
      }),
    },
  };
});

describe("Observability screen enhancements", () => {
  it("renders telemetry summary tiles and filter controls when AI calls exist", async () => {
    render(<ObservabilityPage />);

    // Check headings
    expect(screen.getByRole("heading", { name: "Observability" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI calls" })).toBeInTheDocument();

    // Summary cards
    expect(await screen.findByText("Latency Trend")).toBeInTheDocument();
    expect(screen.getByText("Tokens / Call")).toBeInTheDocument();
    expect(screen.getByText("Validator Accepted")).toBeInTheDocument();

    // Latency sparkline img
    expect(screen.getByRole("img", { name: /Diagnosis latency trend/ })).toBeInTheDocument();
    // Tokens sparkline img
    expect(screen.getByRole("img", { name: /Tokens per call/ })).toBeInTheDocument();

    // Check table has all calls initially
    expect(screen.getByText("Showing 3 of 3 calls")).toBeInTheDocument();
    expect(screen.getByText("INC-101")).toBeInTheDocument();
    expect(screen.getByText("INC-102")).toBeInTheDocument();
    expect(screen.getByText("INC-103")).toBeInTheDocument();
  });

  it("filters AI calls interactively by validator verdict", async () => {
    const user = userEvent.setup();
    render(<ObservabilityPage />);

    await screen.findByText("Showing 3 of 3 calls");

    const verdictSelect = screen.getByLabelText(/Verdict:/i);
    await user.selectOptions(verdictSelect, "refused");

    expect(screen.getByText("Showing 1 of 3 calls")).toBeInTheDocument();
    expect(screen.getByText("INC-102")).toBeInTheDocument();
    expect(screen.queryByText("INC-101")).not.toBeInTheDocument();
  });

  it("filters AI calls interactively by model", async () => {
    const user = userEvent.setup();
    render(<ObservabilityPage />);

    await screen.findByText("Showing 3 of 3 calls");

    const modelSelect = screen.getByLabelText(/Model:/i);
    await user.selectOptions(modelSelect, "mistral:7b");

    expect(screen.getByText("Showing 1 of 3 calls")).toBeInTheDocument();
    expect(screen.getByText("INC-103")).toBeInTheDocument();
    expect(screen.queryByText("INC-101")).not.toBeInTheDocument();
  });

  it("renders alerts with severity badges and refusal details", async () => {
    render(<ObservabilityPage />);

    expect(await screen.findByText("1 firing")).toBeInTheDocument();
    expect(screen.getByText("WARNING")).toBeInTheDocument();
    expect(screen.getByText("High recovery duration threshold approached")).toBeInTheDocument();
    expect(screen.getByText(/permit refused for concurrent runs/)).toBeInTheDocument();
  });
});

describe("Dashboard telemetry visualizations", () => {
  it("renders healthy dependencies meter in SystemHealth", () => {
    render(<SystemHealth system={fx.system} error="" />);

    expect(screen.getByText("Dependencies")).toBeInTheDocument();
    expect(screen.getByText(/7\/7 ok/)).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Healthy dependencies ratio/ }),
    ).toBeInTheDocument();
  });

  it("renders repair success bullet meter in SystemHealth when fleet metrics are available", () => {
    render(<SystemHealth system={fx.system} error="" metrics={fx.metrics} />);

    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Repair success/ }),
    ).toBeInTheDocument();
  });

  it("renders fast quality budget meter and case probe latencies in VerificationStrip", () => {
    render(
      <VerificationStrip
        verification={fx.resolvedIncident.verification ?? null}
        incident={fx.resolvedIncident}
      />,
    );

    // Fast quality budget meter
    expect(
      screen.getByRole("img", { name: /Quality evaluation duration/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Fast quality budget/)).toBeInTheDocument();

    // Case latency distribution
    expect(
      screen.getByRole("img", { name: /Case probe latencies/ }),
    ).toBeInTheDocument();
  });
});
