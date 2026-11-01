/**
 * Reusable lightweight SVG Sparkline and telemetry visualization.
 *
 * Designed for Midnight Operations:
 * - High contrast against deep charcoal/slate surfaces.
 * - Supports line trends, compact vertical bar distributions, and bullet/ratio meters.
 * - Handles edge cases honestly: empty datasets, single data points, constant values,
 *   zeros, negative numbers, and invalid/NaN samples.
 * - Full accessibility: SVG role="img", aria-label with summary metrics, accessible descriptions.
 * - No external charting dependencies — pure, performant SVG.
 */

"use client";

import { useId, useMemo } from "react";

export type SparklineType = "line" | "bar" | "bullet";

export interface SparklineProps {
  /** Sequence of numeric values to visualize */
  data: (number | null | undefined)[];
  /** Chart type: "line" (default), "bar" (vertical distribution), or "bullet" (progress/meter) */
  type?: SparklineType;
  /** Width in pixels or CSS value string (default: "100%") */
  width?: number | string;
  /** Height in pixels (default: 28) */
  height?: number;
  /** Primary accent color (default: "var(--k-state-healing)") */
  color?: string;
  /** Optional secondary or fill color */
  fillColor?: string;
  /** Accessible label describing what the chart represents */
  label?: string;
  /** Measurement unit for text labels and aria descriptions (e.g. "s", "tokens", "%") */
  unit?: string;
  /** Target threshold value (e.g. for bullet meters or latency budgets) */
  threshold?: number;
  /** Optional explicit minimum scale bound */
  min?: number;
  /** Optional explicit maximum scale bound */
  max?: number;
  /** Show endpoint / latest value text alongside the chart */
  showEndpoints?: boolean;
  /** Custom CSS class */
  className?: string;
}

export function Sparkline({
  data,
  type = "line",
  width = "100%",
  height = 28,
  color = "var(--k-state-healing)",
  fillColor,
  label = "Telemetry trend",
  unit = "",
  threshold,
  min: customMin,
  max: customMax,
  showEndpoints = false,
  className,
}: SparklineProps) {
  const gradientId = useId();

  // Sanitize data: filter out non-finite numbers
  const validData = useMemo(() => {
    return data.filter(
      (v): v is number => typeof v === "number" && Number.isFinite(v),
    );
  }, [data]);

  const count = validData.length;

  // Compute scale boundaries
  const { minVal, maxVal, latestVal } = useMemo(() => {
    if (count === 0) {
      return { minVal: 0, maxVal: 0, latestVal: null };
    }
    const computedMin = customMin !== undefined ? customMin : Math.min(...validData);
    const computedMax = customMax !== undefined ? customMax : Math.max(...validData);
    const latest = validData[count - 1] ?? null;
    return {
      minVal: computedMin,
      maxVal: computedMax,
      latestVal: latest,
    };
  }, [validData, count, customMin, customMax]);

  // Accessible summary string
  const ariaDescription = useMemo(() => {
    if (count === 0) return `${label}: No telemetry data available`;
    if (count === 1) return `${label}: single reading of ${latestVal}${unit}`;
    const formattedLatest = latestVal !== null ? `${latestVal}${unit}` : "";
    return `${label}: ${count} samples, latest ${formattedLatest}, range ${minVal}${unit} to ${maxVal}${unit}`;
  }, [label, count, latestVal, minVal, maxVal, unit]);

  // Viewport padding for line chart so stroke doesn't clip
  const padX = 4;
  const padY = 4;
  const viewWidth = 120;
  const viewHeight = height;
  const drawWidth = viewWidth - padX * 2;
  const drawHeight = Math.max(1, viewHeight - padY * 2);

  // 1. EMPTY STATE
  if (count === 0) {
    return (
      <div
        role="img"
        aria-label={ariaDescription}
        className={className}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          width: typeof width === "number" ? `${width}px` : width,
          height: `${height}px`,
        }}
      >
        <svg
          viewBox={`0 0 ${viewWidth} ${viewHeight}`}
          width="100%"
          height={height}
          style={{ overflow: "visible", flex: "1 1 auto" }}
        >
          <line
            x1={padX}
            y1={viewHeight / 2}
            x2={viewWidth - padX}
            y2={viewHeight / 2}
            stroke="var(--k-border)"
            strokeDasharray="3 3"
            strokeWidth={1}
          />
        </svg>
        <span
          className="k-mono-sm k-faint"
          style={{ fontSize: 11, whiteSpace: "nowrap" }}
        >
          no data
        </span>
      </div>
    );
  }

  // 2. BULLET / METER TYPE
  if (type === "bullet") {
    const val = latestVal ?? 0;
    const targetMax = maxVal > minVal ? maxVal : threshold ? threshold * 1.2 : Math.max(val, 1);
    const pct = Math.max(0, Math.min(100, ((val - minVal) / (targetMax - minVal)) * 100));
    const threshPct =
      threshold !== undefined
        ? Math.max(0, Math.min(100, ((threshold - minVal) / (targetMax - minVal)) * 100))
        : null;

    const isExceeded = threshold !== undefined && val > threshold;
    const barColor = isExceeded ? "var(--k-risk-high)" : color;

    return (
      <div
        role="img"
        aria-label={ariaDescription}
        className={className}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          width: typeof width === "number" ? `${width}px` : width,
          height: `${height}px`,
        }}
      >
        <div
          style={{
            position: "relative",
            flex: 1,
            height: 8,
            borderRadius: "var(--k-radius-full)",
            background: "var(--k-surface-sunken)",
            border: "1px solid var(--k-border)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              bottom: 0,
              width: `${pct}%`,
              background: barColor,
              borderRadius: "var(--k-radius-full)",
              transition: "width var(--k-dur-base) var(--k-ease)",
            }}
          />
          {threshPct !== null && (
            <div
              title={`Budget threshold: ${threshold}${unit}`}
              style={{
                position: "absolute",
                top: 0,
                bottom: 0,
                left: `${threshPct}%`,
                width: 2,
                background: "var(--k-risk-med)",
                zIndex: 2,
              }}
            />
          )}
        </div>
        {showEndpoints && (
          <span
            className="k-mono-sm"
            style={{ fontSize: 11, color: isExceeded ? "var(--k-risk-high)" : "var(--k-text-muted)" }}
          >
            {val}
            {unit}
            {threshold !== undefined && ` / ${threshold}${unit}`}
          </span>
        )}
      </div>
    );
  }

  // 3. BAR DISTRIBUTION TYPE
  if (type === "bar") {
    const range = maxVal - minVal;
    const barGap = 3;
    const totalGaps = (count - 1) * barGap;
    const barWidth = Math.max(3, Math.min(16, (drawWidth - totalGaps) / count));
    const totalBarsWidth = count * barWidth + totalGaps;
    const startX = padX + Math.max(0, (drawWidth - totalBarsWidth) / 2);

    return (
      <div
        role="img"
        aria-label={ariaDescription}
        className={className}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          width: typeof width === "number" ? `${width}px` : width,
          height: `${height}px`,
        }}
      >
        <svg
          viewBox={`0 0 ${viewWidth} ${viewHeight}`}
          width="100%"
          height={height}
          style={{ overflow: "visible", flex: "1 1 auto" }}
        >
          {validData.map((val, idx) => {
            const normalizedHeight =
              range === 0
                ? drawHeight * 0.5
                : Math.max(2, ((val - minVal) / range) * drawHeight);
            const x = startX + idx * (barWidth + barGap);
            const y = padY + drawHeight - normalizedHeight;
            const isLatest = idx === count - 1;
            const barFill = isLatest ? color : "var(--k-border-strong)";

            return (
              <rect
                key={idx}
                x={x}
                y={y}
                width={barWidth}
                height={normalizedHeight}
                rx={1.5}
                fill={barFill}
                style={{
                  transition: "all var(--k-dur-base) var(--k-ease)",
                }}
              >
                <title>{`Sample ${idx + 1}: ${val}${unit}`}</title>
              </rect>
            );
          })}
        </svg>
        {showEndpoints && latestVal !== null && (
          <span
            className="k-mono-sm"
            style={{ fontSize: 11, color: "var(--k-text-muted)", flexShrink: 0 }}
          >
            {latestVal}
            {unit}
          </span>
        )}
      </div>
    );
  }

  // 4. LINE CHART (Default)
  // Single point case
  if (count === 1) {
    return (
      <div
        role="img"
        aria-label={ariaDescription}
        className={className}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          width: typeof width === "number" ? `${width}px` : width,
          height: `${height}px`,
        }}
      >
        <svg
          viewBox={`0 0 ${viewWidth} ${viewHeight}`}
          width="100%"
          height={height}
          style={{ overflow: "visible", flex: "1 1 auto" }}
        >
          <line
            x1={padX}
            y1={viewHeight / 2}
            x2={viewWidth - padX}
            y2={viewHeight / 2}
            stroke="var(--k-border-subtle)"
            strokeWidth={1}
          />
          <circle
            cx={viewWidth / 2}
            cy={viewHeight / 2}
            r={3.5}
            fill={color}
            stroke="var(--k-surface)"
            strokeWidth={1.5}
          />
        </svg>
        {showEndpoints && latestVal !== null && (
          <span
            className="k-mono-sm"
            style={{ fontSize: 11, color: "var(--k-text-muted)" }}
          >
            {latestVal}
            {unit}
          </span>
        )}
      </div>
    );
  }

  // Line with 2+ points
  const range = maxVal - minVal;
  const points = validData.map((val, idx) => {
    const x = padX + (idx / (count - 1)) * drawWidth;
    // If range is zero (all points equal), center vertically
    const y =
      range === 0
        ? padY + drawHeight / 2
        : padY + drawHeight - ((val - minVal) / range) * drawHeight;
    return { x, y, val };
  });

  const pathD = points.reduce((acc, pt, idx) => {
    return idx === 0 ? `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}` : `${acc} L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
  }, "");

  // Area path for gradient under the line
  const lastPt = points[points.length - 1]!;
  const firstPt = points[0]!;
  const areaD = `${pathD} L ${lastPt.x.toFixed(1)} ${viewHeight - padY} L ${firstPt.x.toFixed(1)} ${viewHeight - padY} Z`;

  return (
    <div
      role="img"
      aria-label={ariaDescription}
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        width: typeof width === "number" ? `${width}px` : width,
        height: `${height}px`,
      }}
    >
      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        width="100%"
        height={height}
        style={{ overflow: "visible", flex: "1 1 auto" }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={fillColor || color} stopOpacity={0.25} />
            <stop offset="100%" stopColor={fillColor || color} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* Fill Area Under Trend */}
        <path d={areaD} fill={`url(#${gradientId})`} />

        {/* Stroke Line */}
        <path
          d={pathD}
          fill="none"
          stroke={color}
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Latest End-point Marker */}
        <circle
          cx={lastPt.x}
          cy={lastPt.y}
          r={2.5}
          fill={color}
          stroke="var(--k-surface)"
          strokeWidth={1}
        />
      </svg>

      {showEndpoints && latestVal !== null && (
        <span
          className="k-mono-sm"
          style={{
            fontSize: 11,
            color: "var(--k-text-muted)",
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}
        >
          {latestVal}
          {unit}
        </span>
      )}
    </div>
  );
}
