/**
 * The console must recover when it starts before the API does.
 *
 * THE BUG THIS PINS, found 2026-11-05 by driving a real browser.
 *
 * `useIncidents` and `useSafetyState` loaded once on mount and wrote
 * `if (data) setX(data)`, so a failed fetch silently did nothing and nothing
 * ever tried again. Loading the console while the API was down and then
 * bringing the API up left the page showing an empty system - no Fleet
 * section at all, and an incident list reading "Kavach is watching one
 * project and has run no loop yet" - while the API served 82 incidents and
 * `available: true`. Only a page reload fixed it. The dependencies panel
 * recovered on its own, because that one is on a 5s interval, which is what
 * made the failure look like missing data rather than a broken page.
 *
 * `make up` starts the console and the API together and the API waits for
 * Postgres to be healthy, so losing that race is ordinary, not exotic. On
 * demo day it shows a control plane with no history.
 *
 * WHAT MUST NOT CHANGE. The fix retries only until the first success and
 * then stops. `lib/live.ts`'s header makes the case against polling these
 * two - "polling them would be noise" - and that case is still right. The
 * last test here is the one that holds the line: once loaded, no further
 * requests.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { GET, PUT, POST } = vi.hoisted(() => ({
  GET: vi.fn(),
  PUT: vi.fn(),
  POST: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { GET, PUT, POST } };
});

import { useIncidents, useSafetyState, useSystem } from "@/lib/live";

const INCIDENT = {
  incident_id: "INC-000001",
  status: "RESOLVED",
  service: "backend",
  fault_class: "F08",
};
const METRICS = { available: true, incidents: 82, mttr_seconds: 54.2 };
const MODE = { mode: "APPROVAL", enforced: true };

/**
 * What `api.GET` ACTUALLY does when the API is not answering: it REJECTS.
 *
 * This was wrong in the first version of this file, and the mistake is worth
 * keeping visible. It mocked failure as a resolved `{ data: undefined }`,
 * the three tests below passed, the fix shipped - and the real browser
 * still showed an empty console, because `fetch` to a closed port throws
 * and a `.then`-only retry never ran. The browser console said
 * `TypeError: Failed to fetch` thrown straight out of `Object.GET`.
 *
 * A mock that does not match the failure it stands for validates a fix that
 * does not work. Both shapes are now exercised: `down()` is reality, and
 * `EMPTY` covers a 200 that carries no body.
 */
const down = (): Promise<never> =>
  Promise.reject(new TypeError("Failed to fetch"));
const EMPTY = { data: undefined, error: { message: "no body" } };

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
  POST.mockReset();
});

describe("the console started before the API", () => {
  it("retries the incident list until the API answers", async () => {
    GET.mockRejectedValueOnce(new TypeError("Failed to fetch")) // API down
      .mockResolvedValue({ data: [INCIDENT], error: undefined });

    const { result } = renderHook(() => useIncidents(""));
    expect(result.current.incidents).toEqual([]);

    await waitFor(
      () => expect(result.current.incidents).toHaveLength(1),
      { timeout: 6000 },
    );
    expect(result.current.incidents[0]).toMatchObject({
      incident_id: "INC-000001",
    });
  });

  it("retries the fleet metrics until the API answers", async () => {
    GET.mockImplementationOnce(down)
      .mockResolvedValueOnce(EMPTY)
      .mockImplementation((path: string) =>
        Promise.resolve(
          path === "/v1/metrics"
            ? { data: METRICS, error: undefined }
            : { data: MODE, error: undefined },
        ),
      );

    const { result } = renderHook(() => useSafetyState());
    expect(result.current.metrics).toBeNull();

    await waitFor(
      () => expect(result.current.metrics).toMatchObject({ available: true }),
      { timeout: 6000 },
    );
    expect(result.current.mode).toMatchObject({ mode: "APPROVAL" });
  });

  it("treats a half-answer as not ready", async () => {
    // Mode answers, metrics does not. Showing a mode beside an absent Fleet
    // section is the half-loaded state this retry exists to leave behind.
    let metricsDown = true;
    GET.mockImplementation((path: string) => {
      if (path !== "/v1/metrics") {
        return Promise.resolve({ data: MODE, error: undefined });
      }
      if (metricsDown) {
        metricsDown = false;
        return Promise.resolve(EMPTY);
      }
      return Promise.resolve({ data: METRICS, error: undefined });
    });

    const { result } = renderHook(() => useSafetyState());
    await waitFor(
      () => expect(result.current.metrics).toMatchObject({ available: true }),
      { timeout: 6000 },
    );
  });
});

describe("the steady state is unchanged", () => {
  it("stops once loaded, and does not poll", async () => {
    GET.mockResolvedValue({ data: [INCIDENT], error: undefined });

    const { result } = renderHook(() => useIncidents(""));
    await waitFor(() => expect(result.current.incidents).toHaveLength(1));

    const afterFirstLoad = GET.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 2500));
    expect(GET.mock.calls.length).toBe(afterFirstLoad);
  });
});

describe("the health panel when the control plane is gone", () => {
  /**
   * THE WORST OF THE THREE, because this panel's only job is to report health.
   *
   * Measured 2026-11-05 with the API stopped and the page already loaded:
   * eight dependency rows, all green, including "Kavach control plane - ok",
   * while that control plane was not running. `useSystem` had the right
   * message ready and never showed it, because it tested `err || !data` and
   * the real failure arrives as a rejection. The panel went on rendering its
   * last good reading with nothing to say it was stale.
   */
  it("says so, rather than holding the last good reading", async () => {
    GET.mockResolvedValueOnce({
      data: { project: "simple-rag", dependencies: [] },
      error: undefined,
    });

    const { result } = renderHook(() => useSystem());
    await waitFor(() => expect(result.current.system).not.toBeNull());
    expect(result.current.error).toBe("");

    // The control plane goes away.
    GET.mockImplementation(down);
    await waitFor(() => expect(result.current.error).toMatch(/Cannot reach/), {
      timeout: 12000,
    });
    // 15s: the health probe is on a 5s interval, so the failure cannot be
    // observed inside vitest's 5s default.
  }, 15000);
});
