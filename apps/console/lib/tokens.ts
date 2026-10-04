/**
 * Design tokens as TypeScript constants (DESIGN_SYSTEM.md §2, and the
 * ROADMAP P4 deliverable "design tokens as CSS variables and TS constants").
 *
 * These are CSS variable *references*, not duplicated hex values. Copying the
 * palette here would create a second source of truth that drifts from
 * globals.css the first time a token changes — and the theme swap happens in
 * CSS, so a literal hex would simply be wrong in light mode.
 */

export const STATE_TOKENS = {
  DETECTED: "--k-state-detected",
  NO_FAULT: "--k-state-resolved",
  HEALING: "--k-state-healing",
  RESOLVED: "--k-state-resolved",
  ESCALATED: "--k-state-escalated",
  COLLECTING: "--k-state-collecting",
  DIAGNOSING: "--k-state-diagnosing",
  VERIFYING: "--k-state-verifying",
  AWAITING: "--k-state-awaiting",
  ROLLED_BACK: "--k-state-rolledback",
} as const;

export const RISK_TOKENS = {
  LOW: { fg: "--k-risk-low", bg: "--k-risk-low-bg" },
  MEDIUM: { fg: "--k-risk-med", bg: "--k-risk-med-bg" },
  HIGH: { fg: "--k-risk-high", bg: "--k-risk-high-bg" },
  DENIED: { fg: "--k-risk-denied", bg: "--k-risk-denied-bg" },
} as const;

export const SPACE = {
  1: "var(--k-space-1)",
  2: "var(--k-space-2)",
  3: "var(--k-space-3)",
  4: "var(--k-space-4)",
  5: "var(--k-space-5)",
  6: "var(--k-space-6)",
  7: "var(--k-space-7)",
  8: "var(--k-space-8)",
} as const;

export const RADIUS = {
  sm: "var(--k-radius-sm)",
  md: "var(--k-radius-md)",
  lg: "var(--k-radius-lg)",
  full: "var(--k-radius-full)",
} as const;

export const DURATION = {
  fast: "var(--k-dur-fast)",
  base: "var(--k-dur-base)",
  slow: "var(--k-dur-slow)",
} as const;

export const BREAKPOINTS = { sm: 640, md: 1024, lg: 1280, xl: 1600 } as const;

/** The seven Loop Ring stages, in order (§7.1). */
export const LOOP_STAGES = [
  "collect",
  "diagnose",
  "plan",
  "gate",
  "execute",
  "verify",
  "learn",
] as const;

export type LoopStage = (typeof LOOP_STAGES)[number];

/** `var(--token)` for a token name. */
export const cssVar = (token: string): string => `var(${token})`;

export type IncidentState = keyof typeof STATE_TOKENS;
export type RiskTier = keyof typeof RISK_TOKENS;

export const stateVar = (status: string): string =>
  cssVar(STATE_TOKENS[status as IncidentState] ?? "--k-text-muted");

export const riskVars = (tier: string): { fg: string; bg: string } => {
  const key = tier.toUpperCase() as RiskTier;
  const pair = RISK_TOKENS[key] ?? RISK_TOKENS.DENIED;
  return { fg: cssVar(pair.fg), bg: cssVar(pair.bg) };
};
