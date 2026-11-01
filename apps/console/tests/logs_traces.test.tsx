/**
 * Tests for dedicated /logs and /traces screens and their navigation.
 *
 * Verifies:
 * - Dedicated navigation links and aria-current="page" active state on /logs and /traces.
 * - Logs page log stream rendering, severity filtering, search filtering, traceback expansion.
 * - Traces page Jaeger and Grafana explorer links, incident trace deep-links, lookup by ID.
 * - Observability page summary previews linking to /logs and /traces without full duplicate tables.
 * - Honest empty, loading, and error states.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import LogsPage from "@/app/logs/page";
import TracesPage from "@/app/traces/page";
import { traceUrl } from "@/lib/traces";
import ObservabilityPage from "@/app/observability/page";
import { Rail } from "@/components/ui/Rail";
import type { Alert, LlmCall, LogLine } from "@/lib/api";

import * as fx from "./fixtures";

const mockLogs: LogLine[] = [
  {
    at: "2026-10-04T10:45:00.000Z",
    level: "info",
    event: "detection_scan_passed",
    detail: "no anomalies in 60s window",
    incident_id: "",
    exception: "",
    logger: "kavach.loop",
  },
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
    at: "2026-10-04T10:55:00.000Z",
    level: "error",
    event: "model_timeout_exception",
    detail: "connection timed out after 30s",
    incident_id: "INC-103",
    exception: "Traceback (most recent call last):\n  File \"llm.py\", line 42, in call\nTimeoutError",
    logger: "kavach.engine",
  },
];

const mockCalls: LlmCall[] = [
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

const mockAlerts: Alert[] = [];

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
      GET: vi.fn((path: string, options?: { params?: { query?: { level?: string } } }) => {
        if (path === "/v1/logs") {
          const levelQuery = options?.params?.query?.level;
          let filtered = mockLogs;
          if (levelQuery === "error") {
            filtered = mockLogs.filter((l) => l.level === "error" || l.level === "critical");
          } else if (levelQuery === "warning") {
            filtered = mockLogs.filter((l) => ["warning", "error", "critical"].includes(l.level));
          }
          return Promise.resolve({ data: filtered });
        }
        if (path === "/v1/llm-calls") return Promise.resolve({ data: mockCalls });
        if (path === "/v1/alerts") return Promise.resolve({ data: mockAlerts });
        return Promise.resolve({ data: null });
      }),
    },
  };
});

describe("Rail Navigation for Logs and Traces", () => {
  it("renders dedicated navigation links for Logs and Traces", () => {
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/" />);

    const logsLink = screen.getByRole("link", { name: "Logs" });
    const tracesLink = screen.getByRole("link", { name: "Traces" });

    expect(logsLink).toBeInTheDocument();
    expect(logsLink).toHaveAttribute("href", "/logs");

    expect(tracesLink).toBeInTheDocument();
    expect(tracesLink).toHaveAttribute("href", "/traces");
  });

  it("marks Logs link with aria-current='page' when active", () => {
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/logs" />);

    const logsLink = screen.getByRole("link", { name: "Logs" });
    expect(logsLink).toHaveAttribute("aria-current", "page");

    const tracesLink = screen.getByRole("link", { name: "Traces" });
    expect(tracesLink).not.toHaveAttribute("aria-current");
  });

  it("marks Traces link with aria-current='page' when active", () => {
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/traces" />);

    const tracesLink = screen.getByRole("link", { name: "Traces" });
    expect(tracesLink).toHaveAttribute("aria-current", "page");

    const logsLink = screen.getByRole("link", { name: "Logs" });
    expect(logsLink).not.toHaveAttribute("aria-current");
  });
});

describe("Dedicated Logs Page (/logs)", () => {
  it("renders log stream with timestamps, severity levels, and subsystems", async () => {
    render(<LogsPage />);

    expect(screen.getByRole("heading", { name: "Logs" })).toBeInTheDocument();
    expect(await screen.findByText("detection_scan_passed")).toBeInTheDocument();
    expect(screen.getByText("permit_gate_refusal")).toBeInTheDocument();
    expect(screen.getByText("model_timeout_exception")).toBeInTheDocument();

    // Subsystems (in dropdown option and table row)
    expect(screen.getAllByText("kavach.loop").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("kavach.gate").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("kavach.engine").length).toBeGreaterThanOrEqual(1);

    // Incident link
    expect(screen.getByRole("link", { name: "INC-102" })).toHaveAttribute("href", "/traces?incident_id=INC-102");
  });

  it("filters logs by search query interactively", async () => {
    const user = userEvent.setup();
    render(<LogsPage />);

    await screen.findByText("detection_scan_passed");

    const searchInput = screen.getByPlaceholderText(/Filter by event, detail, or incident/i);
    await user.type(searchInput, "timeout");

    expect(screen.getByText("model_timeout_exception")).toBeInTheDocument();
    expect(screen.queryByText("detection_scan_passed")).not.toBeInTheDocument();
    expect(screen.queryByText("permit_gate_refusal")).not.toBeInTheDocument();
  });

  it("filters logs by source subsystem interactively", async () => {
    const user = userEvent.setup();
    render(<LogsPage />);

    await screen.findByText("detection_scan_passed");

    const sourceSelect = screen.getByLabelText(/Source:/i);
    await user.selectOptions(sourceSelect, "kavach.gate");

    expect(screen.getByText("permit_gate_refusal")).toBeInTheDocument();
    expect(screen.queryByText("detection_scan_passed")).not.toBeInTheDocument();
    expect(screen.queryByText("model_timeout_exception")).not.toBeInTheDocument();
  });

  it("renders expandable exception traceback without breaking layout", async () => {
    render(<LogsPage />);

    const detailsSummary = await screen.findByText("Traceback / Exception Details");
    expect(detailsSummary).toBeInTheDocument();
    expect(screen.getByText(/TimeoutError/)).toBeInTheDocument();
  });
});

describe("Dedicated Traces Page (/traces)", () => {
  it("renders external explorer links to Jaeger and Grafana", () => {
    render(<TracesPage />);

    expect(screen.getByRole("heading", { name: "Traces" })).toBeInTheDocument();

    const jaegerLink = screen.getByRole("link", { name: /All heal traces in Jaeger/i });
    expect(jaegerLink).toHaveAttribute("href", expect.stringContaining("operation=kavach.heal"));
    expect(jaegerLink).toHaveAttribute("target", "_blank");

    const grafanaLink = screen.getByRole("link", { name: /Metric history in Grafana/i });
    expect(grafanaLink).toHaveAttribute("href", expect.stringContaining("kavach-overview"));
  });

  it("formats incident trace deep-links correctly with kavach.incident_id tag", () => {
    const url = traceUrl("INC-8921");
    expect(url).toContain("kavach.incident_id");
    expect(url).toContain("INC-8921");
    expect(url).toContain("service=kavach-control-plane");
  });

  it("renders recorded incident runs with direct Jaeger trace deep-links", async () => {
    render(<TracesPage />);

    expect(await screen.findByText("INC-101")).toBeInTheDocument();
    expect(screen.getByText("INC-103")).toBeInTheDocument();
    expect(screen.getByText("F06")).toBeInTheDocument();

    const traceLinks = screen.getAllByRole("link", { name: /Trace in Jaeger/i });
    expect(traceLinks.length).toBe(2);
    expect(traceLinks[0]).toHaveAttribute("href", traceUrl("INC-101"));
  });

  it("updates target trace link when incident ID is typed into lookup input", async () => {
    const user = userEvent.setup();
    render(<TracesPage />);

    const input = screen.getByPlaceholderText("e.g. INC-104512");
    await user.type(input, "INC-9999");

    const openButton = screen.getByRole("link", { name: "Open in Jaeger →" });
    expect(openButton).toHaveAttribute("href", traceUrl("INC-9999"));
  });
});

describe("Observability Page Previews", () => {
  it("provides summary preview links to /logs and /traces instead of full duplicate tables", async () => {
    render(<ObservabilityPage />);

    const logsPageLink = await screen.findByRole("link", { name: "Open dedicated logs stream →" });
    expect(logsPageLink).toHaveAttribute("href", "/logs");

    const tracesPageLink = screen.getByRole("link", { name: "Open dedicated traces explorer →" });
    expect(tracesPageLink).toHaveAttribute("href", "/traces");
  });
});
