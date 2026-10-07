import { expect, test, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { UndoStackTimeline } from "../src/components/UndoStackTimeline";

afterEach(cleanup);

test("UndoStackTimeline renders nothing if empty", () => {
  const { container } = render(<UndoStackTimeline undoStack={[]} outcome="RESOLVED" />);
  expect(container.firstChild).toBeNull();
});

test("UndoStackTimeline renders correctly for resolved incident", () => {
  render(
    <UndoStackTimeline 
      undoStack={[
        {
          original_action: { name: "restart_container", params: {} },
          inverse_action: { name: "restart_container", params: {} },
          pre_state_witness: {},
          applied: true
        }
      ]} 
      outcome="RESOLVED" 
    />
  );
  expect(screen.getAllByText("Undo Stack").length).toBeGreaterThan(0);
  expect(screen.getByText("restart_container")).toBeDefined();
});

test("UndoStackTimeline shows unwound state when escalated", () => {
  render(
    <UndoStackTimeline 
      undoStack={[
        {
          original_action: { name: "scale_up", params: {} },
          inverse_action: { name: "scale_down", params: {} },
          pre_state_witness: {},
          applied: true
        }
      ]} 
      outcome="ESCALATED" 
    />
  );
  expect(screen.getAllByText("Undo Stack").length).toBeGreaterThan(0);
  expect(screen.getByText("scale_up")).toBeDefined();
  expect(screen.getByText("↺ Unwound")).toBeDefined();
  expect(screen.getByText("System restored to initial state")).toBeDefined();
});
