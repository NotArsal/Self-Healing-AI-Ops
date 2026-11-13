/**
 * ASCII art — DESIGN_SYSTEM.md §7.12, ADR 0027.
 *
 * What is asserted is the rule, not the look: no value draws nothing, an open
 * incident is never drawn as finished, the number is always printed beside a
 * bar, and every piece of art is hidden from assistive tech while the text
 * beside it still carries the facts.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HistoryTable, IncidentStream } from "@/components/incident/IncidentStream";
import { VerificationStrip } from "@/components/incident/VerificationStrip";
import { Rail } from "@/components/ui/Rail";
import { BAR_CELLS, bar, seconds } from "@/lib/ascii";

import * as fx from "./fixtures";

describe("bar", () => {
  it("is always BAR_CELLS wide when it draws", () => {
    expect(bar(5, 10)).toHaveLength(BAR_CELLS);
    expect(bar(5, 10)).toBe("█████░░░░░");
  });

  it("draws nothing it cannot draw honestly", () => {
    expect(bar(5, 0)).toBe("");
    expect(bar(-1, 10)).toBe("");
    expect(bar(Number.NaN, 10)).toBe("");
  });

  it("never shows a positive value as empty", () => {
    expect(bar(0.01, 100)).toBe("█░░░░░░░░░");
    expect(bar(0, 100)).toBe("░░░░░░░░░░");
  });

  it("fills and stops when the value is past the max", () => {
    expect(bar(500, 120)).toBe("██████████");
  });
});

describe("seconds", () => {
  it("is null while the incident is open", () => {
    expect(seconds("2026-10-04T10:45:12+00:00", "")).toBeNull();
  });

  it("measures a finished incident", () => {
    expect(seconds(fx.resolvedIncident.detected_at, fx.resolvedIncident.resolved_at)).toBe(56);
  });
});

describe("history durations", () => {
  it("prints the number beside the bar and hides the bar", () => {
    render(<HistoryTable incidents={fx.summaries} />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Duration" })).toBeInTheDocument();
    const art = within(table).getByText("██████████");
    expect(art).toHaveAttribute("aria-hidden", "true");
    expect(art.parentElement).toHaveTextContent("56s");
    expect(screen.getByText(/One cell is 5\.6s/)).toBeInTheDocument();
  });

  // `resolved_at` is set only on RESOLVED, so an empty one is not "open":
  // an APPROVED or NO_FAULT incident is finished and has no end time either.
  it("shows a dash, not \"open\", and no bar when there is no end time", () => {
    render(
      <HistoryTable
        incidents={[{ ...fx.summaries[0]!, status: "APPROVED", resolved_at: "" }]}
      />,
    );
    const table = screen.getByRole("table");
    const col = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent)
      .indexOf("Duration");
    const cell = within(table).getAllByRole("row")[1]!.querySelectorAll("td")[col];
    expect(cell).toHaveTextContent(/^—$/);
    expect(screen.queryByText("open")).not.toBeInTheDocument();
    expect(screen.queryByText(/█/)).not.toBeInTheDocument();
    expect(screen.queryByText(/One cell/)).not.toBeInTheDocument();
  });
});

describe("stream durations", () => {
  const stream = (status: string, resolvedAt: string) =>
    render(
      <IncidentStream
        incidents={[{ ...fx.summaries[0]!, status, resolved_at: resolvedAt }]}
        selectedId=""
        onSelect={() => {}}
        events={[]}
      />,
    );

  it("prints how long a resolved incident took", () => {
    stream("RESOLVED", fx.summaries[0]!.resolved_at);
    expect(screen.getByRole("button")).toHaveTextContent(/56s$/);
  });

  // It counted up to Date.now() for every row without an end time, so an
  // APPROVED row read "5m51s", then "6m02s", for as long as the page was open.
  it("does not count up for a finished row with no end time", () => {
    stream("APPROVED", "");
    const row = screen.getByRole("button");
    expect(row).toHaveTextContent(/—$/);
    expect(row).not.toHaveTextContent(/\d+m\d{2}s|\d+s$/);
  });
});

describe("verification budget", () => {
  it("states the time and the budget in words, with the bar hidden", () => {
    render(
      <VerificationStrip
        verification={fx.resolvedIncident.verification ?? null}
        incident={fx.resolvedIncident}
      />,
    );
    const art = screen.getByText("██░░░░░░░░");
    expect(art).toHaveAttribute("aria-hidden", "true");
    expect(art.parentElement).toHaveTextContent("18.4s of 120s budget");
    expect(art.parentElement).toHaveTextContent("one cell is 12.0s");
    expect(art.parentElement).not.toHaveTextContent("over budget");
  });

  it("says when the run went over budget", () => {
    const v = { ...fx.resolvedIncident.verification!, total_s: 150, within_budget: false };
    render(<VerificationStrip verification={v} incident={fx.resolvedIncident} />);
    expect(screen.getByText("██████████").parentElement).toHaveTextContent(
      "150s of 120s budget, over budget",
    );
  });

  it("draws no budget bar before verification has run", () => {
    render(<VerificationStrip verification={null} incident={null} />);
    expect(screen.queryByText(/█|░/)).not.toBeInTheDocument();
  });
});

describe("decorative still frame", () => {
  it("is hidden from assistive tech, and the sentence still says it all", () => {
    const { container } = render(
      <IncidentStream incidents={[]} selectedId="" onSelect={() => {}} events={[]} />,
    );
    const art = container.querySelector("pre.k-ascii-art");
    expect(art).not.toBeNull();
    expect(art).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText(/No incidents\. Kavach is watching/)).toBeInTheDocument();
  });

  // The list is [] until the first fetch returns, so the empty state used to
  // flash on every page load, and stayed up while the API was down.
  it("is not drawn while the list is still loading", () => {
    const { container } = render(
      <IncidentStream incidents={[]} selectedId="" onSelect={() => {}} events={[]} loading />,
    );
    expect(container.querySelector("pre.k-ascii-art")).toBeNull();
    expect(screen.queryByText(/No incidents/)).not.toBeInTheDocument();
    expect(screen.getByTestId("incidents-skeleton")).toBeInTheDocument();
  });

  it("is gone the moment there is real data", () => {
    const { container } = render(
      <IncidentStream
        incidents={fx.summaries}
        selectedId=""
        onSelect={() => {}}
        events={[]}
      />,
    );
    expect(container.querySelector("pre.k-ascii-art")).toBeNull();
  });
});

describe("rail brand mark", () => {
  it("is flat ink, never the loop gradient (§2.4)", () => {
    const { container } = render(<Rail mode="SIMULATION" modeEnforced={false} current="/" />);
    expect(container.innerHTML).not.toContain("--k-loop-gradient");
  });
});
