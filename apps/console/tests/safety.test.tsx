/**
 * The console's safety surface: the mode switch, the approval panel, and the
 * fleet readouts.
 *
 * The assertions that matter are the refusals — approve disabled until the
 * plan is read, reject disabled without a reason, autonomous confirmed before
 * it takes effect, and a null rate never rendered as a zero.
 */

import { useState } from "react";

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApprovalPanel } from "@/components/safety/ApprovalPanel";
import { ModeSwitch } from "@/components/safety/ModeSwitch";
import { SystemHealth } from "@/components/safety/SystemHealth";
import type { ModeState } from "@/lib/api";

import * as fx from "./fixtures";

/**
 * Zero network, enforced rather than hoped for. Clicking a mode segment or an
 * approve button calls the generated client, and an unstubbed call reaches
 * localhost:8080 for real — which it did on the first run of this file.
 */
// `vi.hoisted` because `vi.mock` is lifted to the top of the file, above any
// plain `const` — which is exactly how this failed the first time.
const { GET, PUT, POST } = vi.hoisted(() => ({
  GET: vi.fn(),
  PUT: vi.fn(),
  POST: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { GET, PUT, POST } };
});

beforeEach(() => {
  GET.mockReset().mockResolvedValue({ data: undefined, error: undefined });
  PUT.mockReset().mockResolvedValue({ data: fx.modeState, error: undefined });
  POST.mockReset().mockResolvedValue({ data: {}, error: undefined });
});

/** jsdom gives every element zero height, so nothing is ever "scrolled to the
 *  end" by default. This makes the plan region report a real geometry. */
function makeScrollable(el: HTMLElement, atEnd: boolean): void {
  Object.defineProperty(el, "scrollHeight", { value: 400, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: 200, configurable: true });
  Object.defineProperty(el, "scrollTop", {
    value: atEnd ? 200 : 0,
    configurable: true,
  });
}

// --- the mode switch --------------------------------------------------------

describe("mode switch", () => {
  function Harness({ initial }: { initial: ModeState }) {
    const [state, setState] = useState(initial);
    return <ModeSwitch state={state} onChanged={setState} />;
  }

  it("renders all three modes as a radio group", () => {
    render(<ModeSwitch state={fx.modeState} onChanged={() => {}} />);
    const group = screen.getByRole("radiogroup");
    expect(within(group).getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByRole("radio", { name: "Approval" })).toBeChecked();
  });

  it("says the mode is enforced, which it now is", () => {
    render(<ModeSwitch state={fx.modeState} onChanged={() => {}} />);
    expect(screen.getByText("enforced")).toBeInTheDocument();
    expect(screen.getByText("yes")).toBeInTheDocument();
  });

  it("names what an empty allow-list means instead of showing nothing", () => {
    render(
      <ModeSwitch
        state={{ ...fx.modeState, allowed_actions: [] }}
        onChanged={() => {}}
      />,
    );
    expect(
      screen.getByText(/an empty allow-list denies everything/),
    ).toBeInTheDocument();
  });

  it("confirms before switching INTO autonomous, listing what it enables", async () => {
    const user = userEvent.setup();
    render(<Harness initial={fx.modeState} />);

    await user.click(screen.getByRole("radio", { name: "Autonomous" }));

    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText(/Switch to autonomous\?/)).toBeInTheDocument();
    // The operator is told exactly which actions become auto-executable.
    expect(within(dialog).getByText("rollback_config")).toBeInTheDocument();
    // And it has NOT taken effect yet.
    expect(screen.getByRole("radio", { name: "Approval" })).toBeChecked();
  });

  it("can be cancelled, leaving the mode untouched", async () => {
    const user = userEvent.setup();
    render(<Harness initial={fx.modeState} />);
    await user.click(screen.getByRole("radio", { name: "Autonomous" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Approval" })).toBeChecked();
  });

  it("does not confirm when moving toward caution", async () => {
    const user = userEvent.setup();
    render(
      <Harness initial={{ ...fx.modeState, mode: "AUTONOMOUS" }} />,
    );
    await user.click(screen.getByRole("radio", { name: "Simulation" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    // It applies immediately instead: moving toward caution never asks.
    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/v1/mode", {
        body: { mode: "SIMULATION" },
      }),
    );
  });

  it("only applies autonomous after the confirmation is accepted", async () => {
    const user = userEvent.setup();
    render(<Harness initial={fx.modeState} />);

    await user.click(screen.getByRole("radio", { name: "Autonomous" }));
    expect(PUT).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Enable autonomous" }));
    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/v1/mode", {
        body: { mode: "AUTONOMOUS" },
      }),
    );
  });

  it("shows the manifest value when the mode was overridden", () => {
    render(
      <ModeSwitch
        state={{ ...fx.modeState, mode: "AUTONOMOUS", overridden: true }}
        onChanged={() => {}}
      />,
    );
    expect(screen.getByText(/overridden for this process/)).toBeInTheDocument();
  });
});

// --- the approval panel -----------------------------------------------------

describe("approval panel", () => {
  it("disables approve until the plan has been read to its end", async () => {
    const user = userEvent.setup();
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);

    const approve = screen.getByRole("button", { name: "Approve repair" });
    expect(approve).toBeDisabled();
    expect(screen.getByText(/Scroll the plan to its end/)).toBeInTheDocument();

    const plan = screen.getByLabelText(/Proposed plan/);
    makeScrollable(plan, true);
    await user.click(plan);
    plan.dispatchEvent(new Event("scroll", { bubbles: true }));

    await waitFor(() => expect(approve).toBeEnabled());
  });

  it("stays disabled when the plan is scrolled but not to the end", async () => {
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);
    const plan = screen.getByLabelText(/Proposed plan/);
    makeScrollable(plan, false);
    plan.dispatchEvent(new Event("scroll", { bubbles: true }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Approve repair" })).toBeDisabled(),
    );
  });

  it("never blocks rejection on having read the plan", () => {
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("requires a reason before a rejection can be sent", async () => {
    const user = userEvent.setup();
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Reject" }));
    const send = screen.getByRole("button", { name: "Reject repair" });
    expect(send).toBeDisabled();

    await user.type(screen.getByLabelText(/Why are you refusing/), "deliberate change");
    expect(send).toBeEnabled();
  });

  it("sends the approval to the incident it is showing", async () => {
    const user = userEvent.setup();
    const onDecided = vi.fn();
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={onDecided} />);

    const plan = screen.getByLabelText(/Proposed plan/);
    makeScrollable(plan, true);
    plan.dispatchEvent(new Event("scroll", { bubbles: true }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Approve repair" })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: "Approve repair" }));

    expect(POST).toHaveBeenCalledWith("/v1/incidents/{incident_id}/approve", {
      params: { path: { incident_id: "INC-110233" } },
    });
    await waitFor(() => expect(onDecided).toHaveBeenCalled());
  });

  it("sends the rejection reason, which the backend also requires", async () => {
    const user = userEvent.setup();
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Reject" }));
    await user.type(screen.getByLabelText(/Why are you refusing/), "looks deliberate");
    await user.click(screen.getByRole("button", { name: "Reject repair" }));

    expect(POST).toHaveBeenCalledWith("/v1/incidents/{incident_id}/reject", {
      params: { path: { incident_id: "INC-110233" } },
      body: { reason: "looks deliberate" },
    });
  });

  it("shows the plan in the fixed order, inverse included", () => {
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);
    const headings = screen
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(headings).toEqual([
      "Diagnosis",
      "Proposed change",
      "Sandbox",
      "Why it stopped here",
      "undo:",
    ]);
  });

  it("says plainly that no sandbox result exists", () => {
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);
    expect(
      screen.getByText(/has not been tried anywhere before you/),
    ).toBeInTheDocument();
  });

  it("explains that approval re-prepares rather than replaying", () => {
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);
    expect(screen.getByText(/not a frozen diff/)).toBeInTheDocument();
  });

  it("shows the risk tier and why the gate stopped", () => {
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(
      screen.getByText(/REQUIRE_APPROVAL under APPROVAL/),
    ).toBeInTheDocument();
  });
});

// --- fleet readouts ---------------------------------------------------------

describe("fleet metrics", () => {
  it("renders MTTR and success rate when there is data", () => {
    render(<SystemHealth system={fx.system} error="" metrics={fx.metrics} />);
    expect(screen.getByText("58.4s")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("MTTR")).toBeInTheDocument();
  });

  it("shows an em dash, never a zero, when a rate has no data", () => {
    render(
      <SystemHealth
        system={fx.system}
        error=""
        metrics={{ ...fx.metrics, mttr_seconds: null, repair_success_rate: null }}
      />,
    );
    // A zero MTTR reads as "instant"; this project must not fabricate that.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("0s")).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("explains the absence when there is no incident store at all", () => {
    render(<SystemHealth system={fx.system} error="" metrics={fx.emptyMetrics} />);
    expect(screen.getByText(/need persisted history/)).toBeInTheDocument();
  });

  it("no longer claims the mode is ungated", () => {
    render(<SystemHealth system={fx.system} error="" metrics={fx.metrics} />);
    expect(screen.getByText(/is enforced/)).toBeInTheDocument();
    expect(screen.queryByText(/does not gate any action/i)).not.toBeInTheDocument();
  });

  it("does not claim enforcement when the backend says there is none", () => {
    // An unreadable manifest means no policy, so nothing may run. Saying
    // "enforced" there would describe a gate that has no rules behind it.
    render(
      <SystemHealth
        system={{ ...fx.system, mode_is_enforced: false }}
        error=""
        metrics={fx.metrics}
      />,
    );
    expect(screen.getByText(/could not be read/)).toBeInTheDocument();
    expect(screen.queryByText(/is enforced/)).not.toBeInTheDocument();
  });
});

// --- accessibility ----------------------------------------------------------

describe("keyboard and labelling", () => {
  it("gives every control in the approval panel an accessible name", () => {
    render(<ApprovalPanel incident={fx.awaitingIncident} onDecided={() => {}} />);
    for (const button of screen.getAllByRole("button")) {
      expect(button).toHaveAccessibleName();
    }
  });

  it("reaches the mode segments by keyboard", async () => {
    const user = userEvent.setup();
    render(<ModeSwitch state={fx.modeState} onChanged={vi.fn()} />);
    await user.tab();
    expect(screen.getByRole("radio", { name: "Simulation" })).toHaveFocus();
  });
});
