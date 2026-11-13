/**
 * A past incident keeps its timeline after the API restarts (2026-11-13).
 *
 * The live feed is the API process's memory; every restart emptied the
 * timeline of every incident. Events are now stored, read back per incident,
 * and merged with the live feed so a line seen both ways shows once.
 */

import { render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { GET, PUT: vi.fn(), POST: vi.fn() } };
});

import OperationsPage from "@/app/page";
import type { LoopEvent } from "@/lib/api";
import { mergeEvents, useStoredEvents } from "@/lib/live";

import * as fx from "./fixtures";

const line = (seq: number, at: string, stage = "detect"): LoopEvent => ({
  seq,
  at,
  incident_id: "INC-1",
  stage,
  status: "ok",
  message: stage,
});

beforeEach(() => GET.mockReset());

describe("stored timeline", () => {
  it("loads the selected incident's events from the store", async () => {
    const stored = [line(1, "2026-11-13T05:44:30.000+00:00")];
    GET.mockResolvedValue({ data: stored, error: undefined });

    const { result } = renderHook(() => useStoredEvents("INC-1"));

    await waitFor(() => expect(result.current).toEqual(stored));
    expect(GET).toHaveBeenCalledWith("/v1/incidents/{incident_id}/events", {
      params: { path: { incident_id: "INC-1" } },
    });
  });

  it("asks for nothing when no incident is selected", () => {
    const { result } = renderHook(() => useStoredEvents(""));
    expect(result.current).toEqual([]);
    expect(GET).not.toHaveBeenCalled();
  });

  it("stays empty, without throwing, when the API is down", async () => {
    GET.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useStoredEvents("INC-1"));
    await waitFor(() => expect(GET).toHaveBeenCalled());
    expect(result.current).toEqual([]);
  });
});

describe("merging stored and live events", () => {
  it("shows a line seen both ways once, in time order", () => {
    const a = line(1, "2026-11-13T05:44:30.000+00:00", "detect");
    const b = line(2, "2026-11-13T05:44:31.000+00:00", "diagnose");
    // After a restart seq starts again at 1, later in time.
    const c = line(1, "2026-11-13T06:00:00.000+00:00", "resolve");

    expect(mergeEvents([a, b], [b, c])).toEqual([a, b, c]);
  });
});

describe("the operations page", () => {
  it("shows a past incident's stored timeline when nothing is live", async () => {
    const id = fx.summaries[0]!.incident_id;
    const stored = { ...line(7, "2026-11-13T05:44:30.000+00:00", "resolve"), incident_id: id,
                     message: "stored line, still here after a restart" };
    GET.mockImplementation((path: string) =>
      Promise.resolve({
        data:
          path === "/v1/incidents"
            ? fx.summaries
            : path === "/v1/incidents/{incident_id}"
              ? fx.resolvedIncident
              : path === "/v1/incidents/{incident_id}/events"
                ? [stored]
                : undefined,
        error: undefined,
      }),
    );

    render(<OperationsPage />);

    expect(
      await screen.findByText("stored line, still here after a restart"),
    ).toBeInTheDocument();
  });
});
