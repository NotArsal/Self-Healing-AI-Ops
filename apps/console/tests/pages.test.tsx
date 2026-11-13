/**
 * The four pages split out of Observability, and the operations screen's
 * link to them (ADR 0029). The API is faked per path; what is asserted is
 * what each page is for, not its look.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { GET, redirect } = vi.hoisted(() => ({ GET: vi.fn(), redirect: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { GET, PUT: vi.fn(), POST: vi.fn() } };
});
vi.mock("next/navigation", () => ({ redirect }));

import HistoryPage from "@/app/history/page";
import LogsPage from "@/app/logs/page";
import MetricsPage from "@/app/metrics/page";
import ObservabilityPage from "@/app/observability/page";
import OperationsPage from "@/app/page";
import TracesPage from "@/app/traces/page";
import type { IncidentSummary } from "@/lib/api";

import * as fx from "./fixtures";

/** Answer each path from `routes`; anything else returns no data. */
const serve = (routes: Record<string, unknown>) =>
  GET.mockImplementation((path: string) =>
    Promise.resolve({ data: routes[path], error: undefined }),
  );

const many = (n: number): IncidentSummary[] =>
  Array.from({ length: n }, (_, i) => ({
    ...fx.summaries[0]!,
    incident_id: `INC-20261113-0000${String(i).padStart(2, "0")}`,
  }));

beforeEach(() => {
  GET.mockReset();
  redirect.mockReset();
  window.history.replaceState({}, "", "/");
});

describe("history page", () => {
  it("lists every stored incident and links each to the operations screen", async () => {
    serve({ "/v1/incidents": fx.summaries });
    render(<HistoryPage />);

    const id = fx.summaries[0]!.incident_id;
    const link = await screen.findByRole("link", { name: id });
    expect(link).toHaveAttribute("href", `/?incident=${id}`);
    expect(GET).toHaveBeenCalledWith("/v1/incidents", { params: { query: { limit: 1000 } } });
  });

  it("says so when the control plane cannot be reached", async () => {
    GET.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<HistoryPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach/);
    expect(screen.getByTestId("history-skeleton")).toBeInTheDocument();
  });
});

describe("logs page", () => {
  const logs = [
    { at: "2026-11-13T05:44:29.000Z", level: "warning", event: "incident store unavailable", detail: "starting up", incident_id: "", exception: "" },
    { at: "2026-11-13T05:44:30.000Z", level: "info", event: "control plane started", detail: "", incident_id: "", exception: "" },
  ];

  it("shows the log, and filters to warnings and above on request", async () => {
    const user = userEvent.setup();
    serve({ "/v1/logs": logs });
    render(<LogsPage />);

    expect(await screen.findByText("control plane started")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Showing everything" }));
    expect(screen.queryByText("control plane started")).not.toBeInTheDocument();
    expect(screen.getByText("incident store unavailable")).toBeInTheDocument();
  });
});

describe("metrics page", () => {
  it("shows fleet figures, per-class rows by catalogue name, and alerts in sentence case", async () => {
    serve({
      "/v1/metrics": fx.metrics,
      "/v1/incidents": fx.summaries,
      "/v1/alerts": [
        { id: "a1", severity: "critical", title: "Breaker open", detail: "d", action: "wait" },
      ],
      "/v1/llm-calls": [],
    });
    render(<MetricsPage />);

    expect(await screen.findByText("82%")).toBeInTheDocument(); // repair success
    const table = await screen.findByRole("table", { name: /per fault class/ });
    expect(within(table).getByText("Retrieval collapse")).toBeInTheDocument();
    expect(await screen.findByText("Critical")).toBeInTheDocument();
    expect(screen.queryByText("CRITICAL")).not.toBeInTheDocument();
    expect(screen.getByText("Fix: wait")).toBeInTheDocument();
  });
});

describe("traces page", () => {
  const id = fx.summaries[0]!.incident_id;
  const events = [
    { seq: 1, at: "2026-11-13T05:44:00.000+00:00", incident_id: id, stage: "run", status: "started", message: "m" },
    { seq: 2, at: "2026-11-13T05:44:01.000+00:00", incident_id: id, stage: "detect", status: "started", message: "m" },
    { seq: 3, at: "2026-11-13T05:44:13.000+00:00", incident_id: id, stage: "detect", status: "ok", message: "m" },
    { seq: 4, at: "2026-11-13T05:44:32.000+00:00", incident_id: id, stage: "resolve", status: "ok", message: "m" },
  ];

  it("opens on the newest run and shows where its time went", async () => {
    serve({ "/v1/incidents": fx.summaries, "/v1/incidents/{incident_id}/events": events });
    render(<TracesPage />);

    const table = await screen.findByRole("table", { name: /Each stage/ });
    const detect = within(table).getByText("detect").closest("tr")!;
    expect(detect).toHaveTextContent("+1.0s");
    expect(detect).toHaveTextContent("12.0s");
    expect(screen.getByText(/Whole run 32.0s/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Jaeger" }).getAttribute("href")).toContain(
      encodeURIComponent(id),
    );
  });

  it("says plainly when a run has no stored events", async () => {
    serve({ "/v1/incidents": fx.summaries, "/v1/incidents/{incident_id}/events": [] });
    render(<TracesPage />);
    expect(await screen.findByText(/No stored events for this run/)).toBeInTheDocument();
  });
});

describe("the old observability address", () => {
  it("lands on Metrics", () => {
    try {
      render(<ObservabilityPage />);
    } catch {
      // A real redirect throws to stop rendering; the mock does not.
    }
    expect(redirect).toHaveBeenCalledWith("/metrics");
  });
});

describe("operations screen", () => {
  it("lists the newest eight and links to the full history", async () => {
    serve({ "/v1/incidents": many(12) });
    render(<OperationsPage />);

    expect(await screen.findByRole("link", { name: "Open the full history" })).toHaveAttribute(
      "href",
      "/history",
    );
    const stream = screen.getByRole("heading", { name: "Incidents" }).closest("section")!;
    expect(within(stream).getAllByRole("listitem")).toHaveLength(8);
  });

  it("names a selected incident with no class as such, not as no incident", async () => {
    const id = "INC-20261113-062558";
    const unclassed = { ...fx.resolvedIncident, incident_id: id, fault_class: null, fault_name: null,
                        status: "ESCALATED" };
    serve({
      "/v1/incidents": [{ ...fx.summaries[0]!, incident_id: id, fault_class: null, status: "ESCALATED" }],
      "/v1/incidents/{incident_id}": unclassed,
    });
    render(<OperationsPage />);
    expect(await screen.findByRole("heading", { level: 1, name: "No fault class" })).toBeInTheDocument();
  });

  it("opens the incident a History link names", async () => {
    window.history.replaceState({}, "", "/?incident=INC-20261113-000011");
    serve({ "/v1/incidents": many(12) });
    render(<OperationsPage />);

    await waitFor(() =>
      expect(GET).toHaveBeenCalledWith("/v1/incidents/{incident_id}", {
        params: { path: { incident_id: "INC-20261113-000011" } },
      }),
    );
  });
});
