/**
 * Data-bound ASCII — DESIGN_SYSTEM.md §7.12 B, ADR 0027.
 *
 * Pure functions from a real value to text. No value, no drawing: callers get
 * "" or null back and render the §8 empty or pending state instead, never a
 * placeholder bar. A bar rounds, so every caller prints the number beside it.
 */

/** Width of every bar. One cell is `max / BAR_CELLS`, and callers say so. */
export const BAR_CELLS = 10;

/**
 * A fixed-width bar for `value` out of `max`.
 *
 * Any positive value gets at least one cell, so "a little" never reads as
 * "nothing". A value past `max` fills the bar and stops there; the caller's
 * text says it overflowed. Returns "" when there is nothing honest to draw.
 */
export function bar(value: number, max: number, cells = BAR_CELLS): string {
  if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0 || value < 0) {
    return "";
  }
  const filled = value === 0 ? 0 : Math.min(cells, Math.max(1, Math.round((value / max) * cells)));
  return "█".repeat(filled) + "░".repeat(cells - filled);
}

/**
 * Seconds between two ISO timestamps, or null while the incident is still open
 * (`resolved_at` is ""). An open incident is never drawn as a finished one.
 */
export function seconds(from: string, to: string): number | null {
  if (!from || !to) return null;
  const s = (new Date(to).getTime() - new Date(from).getTime()) / 1000;
  return Number.isFinite(s) && s >= 0 ? Math.round(s) : null;
}
