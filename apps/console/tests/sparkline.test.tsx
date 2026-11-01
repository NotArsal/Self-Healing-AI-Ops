/**
 * Unit tests for the Sparkline and lightweight telemetry visualization component.
 *
 * Verifies:
 * - Proper handling of valid numeric series.
 * - Single-point readings (honest representation, no trend claims).
 * - Empty, missing, and invalid (NaN / non-finite) data.
 * - Constant and zero-value datasets without division by zero.
 * - Negative and mixed-sign numeric datasets.
 * - Bar distributions and bullet meters.
 * - Full accessibility compliance (role="img", aria-label, readable text tags).
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "@/components/charts/Sparkline";

describe("Sparkline component", () => {
  it("renders a valid line series with SVG path, gradient, and latest marker", () => {
    const { container } = render(
      <Sparkline
        data={[1.2, 0.8, 1.5, 2.0, 1.1]}
        label="LLM Latency"
        unit="s"
        showEndpoints={true}
      />,
    );

    const img = screen.getByRole("img", {
      name: /LLM Latency: 5 samples, latest 1.1s, range 0.8s to 2s/,
    });
    expect(img).toBeInTheDocument();

    const path = container.querySelector("path[stroke]");
    expect(path).toBeInTheDocument();
    expect(path?.getAttribute("d")).toMatch(/^M 4\.0/);

    const circle = container.querySelector("circle");
    expect(circle).toBeInTheDocument();

    expect(screen.getByText("1.1s")).toBeInTheDocument();
  });

  it("handles a single data point without claiming a false trend", () => {
    const { container } = render(
      <Sparkline data={[42]} label="RPS" unit=" req/s" showEndpoints={true} />,
    );

    const img = screen.getByRole("img", {
      name: /RPS: single reading of 42 req\/s/,
    });
    expect(img).toBeInTheDocument();

    // Renders single point circle, no multi-segment line path
    expect(container.querySelector("path[stroke]")).not.toBeInTheDocument();
    expect(container.querySelector("circle")).toBeInTheDocument();
    expect(screen.getByText("42 req/s")).toBeInTheDocument();
  });

  it("handles empty data truthfully with dashed line and no data label", () => {
    render(<Sparkline data={[]} label="Memory usage" />);

    const img = screen.getByRole("img", {
      name: "Memory usage: No telemetry data available",
    });
    expect(img).toBeInTheDocument();
    expect(screen.getByText("no data")).toBeInTheDocument();
  });

  it("filters out invalid, NaN and non-finite values safely", () => {
    render(
      <Sparkline
        data={[10, NaN, undefined, 20, null as unknown as number, Infinity, 30]}
        label="Cleaned"
      />,
    );

    const img = screen.getByRole("img", {
      name: /Cleaned: 3 samples, latest 30, range 10 to 30/,
    });
    expect(img).toBeInTheDocument();
  });

  it("handles constant and zero-value datasets without division-by-zero errors", () => {
    const { container } = render(
      <Sparkline data={[0, 0, 0, 0]} label="Zero series" />,
    );

    const img = screen.getByRole("img", {
      name: /Zero series: 4 samples, latest 0, range 0 to 0/,
    });
    expect(img).toBeInTheDocument();

    const path = container.querySelector("path[stroke]");
    expect(path).toBeInTheDocument();
    // Path should remain valid and flat (all Y coordinates identical)
    expect(path?.getAttribute("d")).not.toContain("NaN");
  });

  it("scales negative and mixed-sign values properly", () => {
    const { container } = render(
      <Sparkline data={[-10, 0, 10, -5, 15]} label="Delta" unit="ms" />,
    );

    const img = screen.getByRole("img", {
      name: /Delta: 5 samples, latest 15ms, range -10ms to 15ms/,
    });
    expect(img).toBeInTheDocument();

    const path = container.querySelector("path[stroke]");
    expect(path?.getAttribute("d")).not.toContain("NaN");
  });

  it("renders a compact bar distribution with rects for discrete samples", () => {
    const { container } = render(
      <Sparkline
        data={[0.2, 0.5, 0.3]}
        type="bar"
        label="Probe latencies"
        unit="s"
        showEndpoints={true}
      />,
    );

    const img = screen.getByRole("img", {
      name: /Probe latencies: 3 samples, latest 0.3s, range 0.2s to 0.5s/,
    });
    expect(img).toBeInTheDocument();

    const rects = container.querySelectorAll("rect");
    expect(rects).toHaveLength(3);
    expect(screen.getByText("0.3s")).toBeInTheDocument();
  });

  it("renders a bullet meter with target threshold and fill percentage", () => {
    render(
      <Sparkline
        data={[1.8]}
        type="bullet"
        threshold={5.0}
        max={6.0}
        label="Execution duration"
        unit="s"
        showEndpoints={true}
      />,
    );

    const img = screen.getByRole("img", {
      name: /Execution duration: single reading of 1.8s/,
    });
    expect(img).toBeInTheDocument();
    expect(screen.getByText("1.8s / 5s")).toBeInTheDocument();
  });
});
