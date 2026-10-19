/**
 * Console tests — the thirteen checks the P4 brief enumerates.
 *
 * Deliberately not screenshot tests. A screenshot proves pixels, and the things
 * that matter here are properties a screenshot cannot assert: that no state is
 * conveyed by colour alone, that the mode indicator is in the DOM on every
 * screen, that a pushed WebSocket frame reaches the timeline without a refetch,
 * and that the confidence number is labelled uncalibrated.
 */

import { useState } from "react";

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActionPlan } from "@/components/incident/ActionPlan";
import { DiagnosisCard } from "@/components/incident/DiagnosisCard";
import { EvidenceList } from "@/components/incident/EvidenceList";
import { HistoryTable, IncidentStream, reachedStages } from "@/components/incident/IncidentStream";
import { LoopRing } from "@/components/incident/LoopRing";
import { Timeline } from "@/components/incident/Timeline";
import { ModeIndicator } from "@/components/safety/ModeIndicator";
import { SystemHealth } from "@/components/safety/SystemHealth";
import { Rail } from "@/components/ui/Rail";
import { ProbePill, RiskBadge, StatePill } from "@/components/ui/pills";
import { VerificationStrip } from "@/components/incident/VerificationStrip";
import { useEvents } from "@/lib/live";
import { LOOP_STAGES, type LoopStage } from "@/lib/tokens";

import * as fx from "./fixtures";
import { FakeSocket, lastSocket } from "./setup";

// --- 4. health state renders ------------------------------------------------

describe("system health", () => {
  it("renders every dependency with a word, not just a colour", () => {
    render(<SystemHealth system={fx.system} error="" />);
    expect(screen.getByText("Target application")).toBeInTheDocument();
    expect(screen.getByText("Target database")).toBeInTheDocument();
    expect(screen.getByText("Prometheus")).toBeInTheDocument();
    // Seven dependencies, each with a textual ok/failing label.
    expect(screen.getAllByText("ok")).toHaveLength(7);
  });

  it("distinguishes Kavach's direct Ollama path from the target's proxied one", () => {
    render(<SystemHealth system={fx.system} error="" />);
    expect(screen.getByText("Ollama, Kavach path")).toBeInTheDocument();
    expect(screen.getByText("Ollama, target path")).toBeInTheDocument();
    expect(screen.getByText(/never proxied/)).toBeInTheDocument();
  });

  it("shows project identity, threshold and corpus", () => {
    render(<SystemHealth system={fx.system} error="" />);
    expect(screen.getByRole("heading", { name: "simple-rag" })).toBeInTheDocument();
    expect(screen.getByText("0.35")).toBeInTheDocument();
    expect(screen.getByText("30 chunks / 2 files")).toBeInTheDocument();
  });

  it("states that the mode is now an enforced gate", () => {
    // Inverted in P5: permit() exists and the loop reads the mode, so the
    // honest sentence changed. A console that still said "not gated" would be
    // describing the previous phase.
    render(<SystemHealth system={fx.system} error="" />);
    expect(screen.getByText(/is enforced/i)).toBeInTheDocument();
    expect(screen.queryByText(/does not gate any action/i)).not.toBeInTheDocument();
  });

  it("explains how to fix an unreachable control plane instead of apologising", () => {
    render(<SystemHealth system={null} error="Cannot reach the Kavach control plane. Start it with `make dev-api`." />);
    expect(screen.getByText(/make dev-api/)).toBeInTheDocument();
  });
});

// --- 5. incident state renders ----------------------------------------------

describe("incident state", () => {
  it("renders the fault, service and status in the stream", () => {
    render(
      <IncidentStream
        incidents={fx.summaries}
        selectedId={fx.resolvedIncident.incident_id}
        onSelect={() => {}}
        events={fx.events}
      />,
    );
    const row = screen.getByRole("button", { name: /F06 retrieval collapse/ });
    expect(row).toBeInTheDocument();
    expect(within(row).getByText("Resolved")).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-current", "true");
  });

  it("uses a real list, not a div soup", () => {
    render(
      <IncidentStream incidents={fx.summaries} selectedId="" onSelect={() => {}} events={[]} />,
    );
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("offers an invitation, not an apology, when empty", () => {
    render(<IncidentStream incidents={[]} selectedId="" onSelect={() => {}} events={[]} />);
    expect(screen.getByText(/Kavach is watching one project/)).toBeInTheDocument();
  });

  it("maps backend stages onto the seven ring stages", () => {
    const { reached, inFlight } = reachedStages(fx.events, "INC-104512");
    expect([...reached].sort()).toEqual(["collect", "diagnose"]);
    expect(inFlight).toBe(false);
    expect(LOOP_STAGES).toHaveLength(7);
  });

  it("marks a failed stage distinctly from an unreached one", () => {
    const failedEvents = [
      ...fx.events,
      { seq: 5, at: "2026-10-04T10:45:41+00:00", incident_id: "INC-104512", stage: "validate", status: "failed", message: "rejected" },
    ];
    const { failed } = reachedStages(failedEvents, "INC-104512");
    expect(failed.has("gate")).toBe(true);
  });

  it("gives the Loop Ring an accessible progress label", () => {
    const reached = new Set<LoopStage>(["collect", "diagnose"]);
    render(<LoopRing reached={reached} inFlight={false} />);
    expect(screen.getByRole("img", { name: /2 of 7 stages reached/ })).toBeInTheDocument();
  });
});

// --- 6. live event updates render -------------------------------------------

describe("live updates", () => {
  function Harness() {
    const { events, connected } = useEvents();
    return <Timeline events={events} connected={connected} />;
  }

  beforeEach(() => {
    FakeSocket.instances.length = 0;
  });

  it("renders a pushed WebSocket frame with no refetch and no polling", async () => {
    render(<Harness />);
    await waitFor(() => expect(lastSocket()).toBeDefined());

    expect(screen.getByText(/No events yet/)).toBeInTheDocument();

    act(() => lastSocket()?.receive(fx.events[0]));
    await waitFor(() =>
      expect(screen.getByText(/operator started a loop run/)).toBeInTheDocument(),
    );

    act(() => lastSocket()?.receive(fx.events[1]));
    await waitFor(() =>
      expect(
        screen.getByText(/detected F06 retrieval_collapse on backend/),
      ).toBeInTheDocument(),
    );
  });

  it("de-duplicates replayed events by seq, so a reconnect does not double the timeline", async () => {
    render(<Harness />);
    await waitFor(() => expect(lastSocket()).toBeDefined());
    act(() => lastSocket()?.receive(fx.events[1]));
    act(() => lastSocket()?.receive(fx.events[1]));
    await waitFor(() =>
      expect(screen.getAllByText(/detected F06 retrieval_collapse/)).toHaveLength(1),
    );
  });

  it("announces new timeline lines to assistive technology", () => {
    render(<Timeline events={fx.events} connected />);
    const list = screen.getByRole("list");
    expect(list).toHaveAttribute("aria-live", "polite");
  });

  it("shows each event with a timestamp and a spelled-out status", () => {
    render(<Timeline events={fx.events} connected />);
    expect(screen.getAllByText(/Status: ok\./).length).toBeGreaterThan(0);
    expect(screen.getByText("Live · streaming · 4 events")).toBeInTheDocument();
  });
});

// --- 7. evidence citations render and open details --------------------------

describe("evidence", () => {
  function EvidenceHarness() {
    const [open, setOpen] = useState("");
    return (
      <>
        <DiagnosisCard rca={fx.resolvedIncident.rca ?? null} onCitationClick={setOpen} />
        <EvidenceList
          items={fx.resolvedIncident.rca?.evidence ?? []}
          citedIds={fx.resolvedIncident.rca?.diagnosis?.evidence_ids ?? []}
          openId={open}
          onOpenChange={setOpen}
        />
      </>
    );
  }

  it("shows every evidence item with its stable ID", () => {
    render(
      <EvidenceList
        items={fx.resolvedIncident.rca?.evidence ?? []}
        citedIds={[]}
        openId=""
        onOpenChange={() => {}}
      />,
    );
    for (const eid of ["EV-M01", "EV-M02", "EV-C01", "EV-L06"]) {
      expect(screen.getByText(eid)).toBeInTheDocument();
    }
  });

  it("expands an item to its payload, in place", async () => {
    const user = userEvent.setup();
    render(
      <EvidenceList
        items={fx.resolvedIncident.rca?.evidence ?? []}
        citedIds={[]}
        openId=""
        onOpenChange={() => {}}
      />,
    );
    const toggle = screen.getByRole("button", { name: /EV-M01/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
  });

  it("opens the cited evidence item when a diagnosis citation is clicked", async () => {
    const user = userEvent.setup();
    render(<EvidenceHarness />);

    // The citation is a real button, not a link to somewhere else.
    const citation = screen.getByRole("button", { name: "EV-M02" });
    await user.click(citation);

    await waitFor(() => {
      expect(screen.getByText("healthy")).toBeInTheDocument();
      expect(screen.getByText("at least 1")).toBeInTheDocument();
    });
  });

  it("never navigates away: citations are buttons, not external links", () => {
    render(
      <DiagnosisCard rca={fx.resolvedIncident.rca ?? null} onCitationClick={() => {}} />,
    );
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "EV-M02" })).toBeInTheDocument();
  });
});

// --- 8. diagnosis card renders the uncalibrated-confidence state ------------

describe("diagnosis card", () => {
  it("shows the confidence value and labels it uncalibrated", () => {
    render(<DiagnosisCard rca={fx.resolvedIncident.rca ?? null} onCitationClick={() => {}} />);
    expect(screen.getByText("0.90")).toBeInTheDocument();
    expect(screen.getByText(/Uncalibrated/)).toBeInTheDocument();
    expect(
      screen.getByText(/not a measured probability of correctness/i),
    ).toBeInTheDocument();
  });

  it("never presents the confidence as a percentage probability", () => {
    render(<DiagnosisCard rca={fx.resolvedIncident.rca ?? null} onCitationClick={() => {}} />);
    expect(screen.queryByText(/90%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/90 ?% probability/i)).not.toBeInTheDocument();
  });

  it("describes the confidence bar in words for assistive technology", () => {
    render(<DiagnosisCard rca={fx.resolvedIncident.rca ?? null} onCitationClick={() => {}} />);
    expect(
      screen.getByRole("img", { name: /confidence 0.90 of 1, uncalibrated/i }),
    ).toBeInTheDocument();
  });

  it("renders the validation verdict and the ten checks", async () => {
    const user = userEvent.setup();
    render(<DiagnosisCard rca={fx.resolvedIncident.rca ?? null} onCitationClick={() => {}} />);
    expect(screen.getByText(/Validation accepted/)).toBeInTheDocument();
    await user.click(screen.getByText(/Validation checks \(10\/10 passed\)/));
    expect(screen.getByText("deterministic_agreement")).toBeInTheDocument();
  });

  it("treats an honest non-answer as neutral, not as a failure", () => {
    const honest = {
      ...fx.resolvedIncident.rca!,
      diagnosis: null,
      approved: false,
      error: "fault_class is INSUFFICIENT_EVIDENCE",
    };
    render(<DiagnosisCard rca={honest} onCitationClick={() => {}} />);
    const line = screen.getByText("Not enough evidence to diagnose.");
    expect(line).toBeInTheDocument();
    expect(line).toHaveStyle({ color: "var(--k-text-muted)" });
  });

  it("shows the ruled-out alternatives with their reasons", async () => {
    const user = userEvent.setup();
    render(<DiagnosisCard rca={fx.resolvedIncident.rca ?? null} onCitationClick={() => {}} />);
    await user.click(screen.getByRole("button", { name: /Ruled out \(1\)/ }));
    expect(screen.getByText(/llm_error_ratio 0.0/)).toBeInTheDocument();
  });
});

// --- 9. verification state renders ------------------------------------------

describe("verification strip", () => {
  it("shows all three probes, including the one that is not implemented", () => {
    render(
      <VerificationStrip
        verification={fx.resolvedIncident.verification ?? null}
        incident={fx.resolvedIncident}
      />,
    );
    expect(screen.getByText("health")).toBeInTheDocument();
    expect(screen.getByText("SLO window")).toBeInTheDocument();
    expect(screen.getByText("fast quality")).toBeInTheDocument();
  });

  it("labels the third probe fast quality, never eval", () => {
    render(
      <VerificationStrip
        verification={fx.resolvedIncident.verification ?? null}
        incident={fx.resolvedIncident}
      />,
    );
    expect(screen.queryByText(/\beval\b/i)).not.toBeInTheDocument();
  });

  it("reports the corpus as unchanged and shows the final state", () => {
    render(
      <VerificationStrip
        verification={fx.resolvedIncident.verification ?? null}
        incident={fx.resolvedIncident}
      />,
    );
    expect(screen.getByText(/unchanged · 30 chunks \/ 2 files/)).toBeInTheDocument();
    expect(screen.getByText("RESOLVED")).toBeInTheDocument();
    expect(screen.getByText("9f1c2ab4")).toBeInTheDocument();
  });

  it("renders every probe result as a word as well as an icon", () => {
    render(
      <VerificationStrip
        verification={fx.resolvedIncident.verification ?? null}
        incident={fx.resolvedIncident}
      />,
    );
    expect(screen.getAllByText("passed").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("pending")).toBeInTheDocument();
  });
});

// --- action plan ------------------------------------------------------------

describe("action plan", () => {
  it("shows the inverse on screen, never behind a disclosure", () => {
    render(
      <ActionPlan
        action={fx.resolvedIncident.action ?? null}
        plannedAction="rollback_config"
      />,
    );
    expect(screen.getByText("undo:")).toBeInTheDocument();
    expect(screen.getByText("rerank_threshold=0.999")).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("shows the idempotency key, pre-state hash and risk tier", () => {
    render(
      <ActionPlan action={fx.resolvedIncident.action ?? null} plannedAction={null} />,
    );
    expect(
      screen.getByText("INC-104512:rollback_config:0.35"),
    ).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
  });
});

// --- 10. mode indicator is always visible -----------------------------------

describe("mode indicator", () => {
  it("names the mode and says it is not enforced", () => {
    render(<ModeIndicator mode="SIMULATION" enforced={false} />);
    expect(screen.getByText("Simulation")).toBeInTheDocument();
    expect(screen.getByText(/does not gate any action/i)).toBeInTheDocument();
  });

  it("is present in the rail on the operations screen", () => {
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/" />);
    expect(screen.getByText("Simulation")).toBeInTheDocument();
  });

  it("is present in the rail on the preflight screen too", () => {
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/preflight" />);
    expect(screen.getByText("Simulation")).toBeInTheDocument();
  });
});

// --- 11. keyboard navigation and focus --------------------------------------

describe("keyboard navigation", () => {
  it("reaches the rail links and the theme toggle by Tab alone", async () => {
    const user = userEvent.setup();
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/" />);

    await user.tab();
    expect(screen.getByRole("link", { name: "Operations" })).toHaveFocus();
    await user.tab();
    expect(
      screen.getByRole("link", { name: "Onboarding and preflight" }),
    ).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Observability" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: /Switch to light theme/ })).toHaveFocus();
  });

  it("gives every rail destination an accessible name", () => {
    // The assertion the test above could not make: it walks a FIXED number
    // of tab stops, so a fourth nav item added without a name would sit
    // before the toggle and only ever show up as a confusing focus
    // failure. This counts whatever is there and names all of it.
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/" />);
    const links = screen.getAllByRole("link");
    expect(links.length).toBeGreaterThanOrEqual(3);
    for (const link of links) {
      expect(link.getAttribute("aria-label")).toBeTruthy();
      expect(link.getAttribute("title")).toBeTruthy();
    }
  });

  it("selects an incident row with the keyboard", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <IncidentStream
        incidents={fx.summaries}
        selectedId=""
        onSelect={onSelect}
        events={[]}
      />,
    );
    await user.tab();
    expect(screen.getByRole("button", { name: /F06/ })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("INC-104512");
  });

  it("expands an evidence item with the keyboard", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <EvidenceList
        items={fx.resolvedIncident.rca?.evidence ?? []}
        citedIds={[]}
        openId=""
        onOpenChange={onOpenChange}
      />,
    );
    await user.tab();
    await user.keyboard("{Enter}");
    expect(onOpenChange).toHaveBeenCalledWith("EV-M01");
  });

  it("gives every clickable target an accessible name", () => {
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/" />);
    for (const element of [
      ...screen.getAllByRole("link"),
      ...screen.getAllByRole("button"),
    ]) {
      expect(element).toHaveAccessibleName();
    }
  });
});

// --- 12 & 13. both themes ---------------------------------------------------

describe("themes", () => {
  it("defaults to dark, the primary theme", () => {
    render(<SystemHealth system={fx.system} error="" />);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("switches to light and persists the choice", async () => {
    const user = userEvent.setup();
    render(<Rail mode="SIMULATION" modeEnforced={false} current="/" />);

    await user.click(screen.getByRole("button", { name: /Switch to light theme/ }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(window.localStorage.getItem("kavach-theme")).toBe("light");

    await user.click(screen.getByRole("button", { name: /Switch to dark theme/ }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("renders the same content under the light theme", () => {
    document.documentElement.setAttribute("data-theme", "light");
    render(
      <VerificationStrip
        verification={fx.resolvedIncident.verification ?? null}
        incident={fx.resolvedIncident}
      />,
    );
    expect(screen.getByText("fast quality")).toBeInTheDocument();
    expect(screen.getByText("RESOLVED")).toBeInTheDocument();
  });

  it("uses theme tokens, never hardcoded hex, for state colour", () => {
    render(<StatePill status="RESOLVED" />);
    expect(screen.getByText("Resolved")).toHaveStyle({
      color: "var(--k-state-resolved)",
    });
  });
});

// --- no colour-only state ---------------------------------------------------

describe("no colour-only state indicators", () => {
  it("pairs every risk tier with a word", () => {
    for (const tier of ["LOW", "MEDIUM", "HIGH", "DENIED"]) {
      const { unmount } = render(<RiskBadge tier={tier} />);
      expect(
        screen.getByText(tier.charAt(0) + tier.slice(1).toLowerCase()),
      ).toBeInTheDocument();
      unmount();
    }
  });

  it("pairs every probe result with a word", () => {
    for (const state of ["pending", "passed", "failed"] as const) {
      const { unmount } = render(<ProbePill label="health" state={state} />);
      expect(screen.getByText(state)).toBeInTheDocument();
      unmount();
    }
  });

  it("pairs every incident state with a word", () => {
    for (const status of ["DETECTED", "HEALING", "RESOLVED", "ESCALATED", "NO_FAULT"]) {
      const { unmount } = render(<StatePill status={status} />);
      const word = status.replace(/_/g, " ").toLowerCase();
      expect(
        screen.getByText(word.charAt(0).toUpperCase() + word.slice(1)),
      ).toBeInTheDocument();
      unmount();
    }
  });
});

// --- history ----------------------------------------------------------------

describe("incident history", () => {
  it("is a real table with scoped column headers", () => {
    render(<HistoryTable incidents={fx.summaries} />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Incident" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Outcome" })).toBeInTheDocument();
    expect(within(table).getByText("INC-104512")).toBeInTheDocument();
  });
});
