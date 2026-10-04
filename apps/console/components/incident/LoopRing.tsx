/**
 * The Loop Ring — DESIGN_SYSTEM.md §7.1.
 *
 * Seven ticks: collect · diagnose · plan · gate · execute · verify · learn.
 * A tick lights only when that stage genuinely started, which is why this takes
 * a reached-set rather than a stage index: the implemented loop validates
 * (gate) before it plans, so an index would light a stage that had not run.
 *
 * The rotating gradient is the only non-user-triggered motion in the product,
 * it runs only while a stage is in flight, and `prefers-reduced-motion` stops
 * it while stage advancement still renders.
 */

import { LOOP_STAGES, type LoopStage } from "@/lib/tokens";

/** Backend event stages map onto the ring's canonical seven. */
const STAGE_MAP: Record<string, LoopStage> = {
  run: "collect",
  detect: "collect",
  evidence: "collect",
  diagnose: "diagnose",
  validate: "gate",
  plan: "plan",
  repair: "execute",
  verify: "verify",
  resolve: "learn",
};

export const ringStage = (eventStage: string): LoopStage | null =>
  STAGE_MAP[eventStage] ?? null;

export function LoopRing({
  reached,
  failed,
  inFlight,
  size = 96,
}: {
  reached: ReadonlySet<LoopStage>;
  failed?: ReadonlySet<LoopStage>;
  inFlight: boolean;
  size?: number;
}) {
  const stroke = size > 40 ? 3 : 2;
  const radius = (size - stroke * 2 - 4) / 2;
  const centre = size / 2;
  const gradientId = `k-ring-${size}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`Loop progress: ${reached.size} of ${LOOP_STAGES.length} stages reached`}
      style={{
        animation: inFlight ? "k-spin 3s linear infinite" : undefined,
        flex: "0 0 auto",
      }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#7c7cf5" />
        </linearGradient>
      </defs>

      <circle
        cx={centre}
        cy={centre}
        r={radius}
        fill="none"
        stroke="var(--k-border)"
        strokeWidth={stroke}
      />

      {LOOP_STAGES.map((stage, index) => {
        // Start at twelve o'clock and run clockwise, so the sequence reads the
        // way the operator reads the timeline beside it.
        const angle = (index / LOOP_STAGES.length) * 2 * Math.PI - Math.PI / 2;
        const tickRadius = size > 40 ? 3.5 : 2;
        const isFailed = failed?.has(stage) ?? false;
        const isReached = reached.has(stage);
        return (
          <circle
            key={stage}
            cx={centre + radius * Math.cos(angle)}
            cy={centre + radius * Math.sin(angle)}
            r={tickRadius}
            fill={
              isFailed
                ? "var(--k-risk-high)"
                : isReached
                  ? `url(#${gradientId})`
                  : "var(--k-border-strong)"
            }
          />
        );
      })}

      {reached.size > 0 && (
        <circle
          cx={centre}
          cy={centre}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${(reached.size / LOOP_STAGES.length) * 2 * Math.PI * radius} ${2 * Math.PI * radius}`}
          transform={`rotate(-90 ${centre} ${centre})`}
        />
      )}
    </svg>
  );
}
