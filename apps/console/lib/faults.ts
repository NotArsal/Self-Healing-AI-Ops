/**
 * One name per fault class, wherever the console shows a fault.
 *
 * The model is told to copy its fault name from the catalogue in
 * `apps/control-plane/kavach/llm/prompts/diagnose.txt`, and it does not
 * always: on 2026-11-13 the store held F08 under three names, and ten F06
 * rows read "Prompt version regression", the name of a different class. The
 * class is what the gate validated, so the console names the class. The
 * stored `fault_name` keeps the model's wording, because the bench measures
 * it (`harness/report.py`, "answer is self-consistent").
 *
 * `tests/faults.test.ts` fails if this copy drifts from the prompt.
 */
export const FAULT_NAMES: Readonly<Record<string, string>> = {
  F01: "Primary LLM endpoint outage",
  F02: "Primary LLM endpoint latency degradation",
  F03: "Container crash-loop or out-of-memory",
  F05: "Database connection pool exhaustion",
  F06: "Retrieval collapse",
  F07: "Prompt version regression",
  F08: "Configuration or environment regression",
  F09: "Token or cost blowout",
};

/** The catalogue name for a class, or the stored wording for a class the
 *  catalogue does not list (so nothing is ever shown blank). */
export const faultName = (
  faultClass: string | null | undefined,
  stored: string | null | undefined = "",
): string =>
  (faultClass ? FAULT_NAMES[faultClass] : undefined) ?? (stored ?? "").replace(/_/g, " ");
