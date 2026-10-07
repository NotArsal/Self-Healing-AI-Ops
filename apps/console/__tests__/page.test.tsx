import { expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import Page from "../src/app/page";

// Mock EventSource for JSDOM
class MockEventSource {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}
vi.stubGlobal("EventSource", MockEventSource);

test("Page renders correctly", () => {
  render(<Page />);
  expect(screen.getByText("Active Incidents")).toBeDefined();
});
