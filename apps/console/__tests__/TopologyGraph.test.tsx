import { expect, test, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { TopologyGraph } from "../src/components/TopologyGraph";

afterEach(cleanup);

test("TopologyGraph renders nothing if empty", () => {
  const { container } = render(<TopologyGraph services={{}} />);
  expect(container.firstChild).toBeNull();
});

test("TopologyGraph renders nodes based on services", () => {
  const mockServices = {
    "web": { role: "frontend", depends_on: ["api"] },
    "api": { role: "backend", depends_on: ["db"] },
    "db": { role: "database" }
  };
  
  render(<TopologyGraph services={mockServices} />);
  expect(screen.getByText("Service Topology")).toBeDefined();
  expect(screen.getByText("web")).toBeDefined();
  expect(screen.getByText("api")).toBeDefined();
  expect(screen.getByText("db")).toBeDefined();
  expect(screen.getByText("frontend")).toBeDefined();
});
