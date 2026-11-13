/**
 * The console's fault names are the catalogue the model is given.
 *
 * Read from the prompt itself, so a renamed class in `diagnose.txt` fails here
 * instead of leaving the console on an old name.
 */

// @vitest-environment node

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { FAULT_NAMES, faultName } from "@/lib/faults";

// Resolved from the vitest root (apps/console), as layout.test.ts does.
const prompt = readFileSync(
  resolve("../control-plane/kavach/llm/prompts/diagnose.txt"),
  "utf8",
);

/** "  F08  Configuration or environment regression. A setting ..." */
const catalogue = Object.fromEntries(
  [...prompt.matchAll(/^ {2}(F\d\d) {2}([^.\n]+)\./gm)].map((m) => [m[1], m[2]!.trim()]),
);

describe("fault names", () => {
  it("parsed a catalogue from the prompt, so the next test checks something", () => {
    expect(Object.keys(catalogue)).toContain("F08");
  });

  it("match the catalogue in diagnose.txt, class for class", () => {
    expect(FAULT_NAMES).toEqual(catalogue);
  });

  it("name the class, not whatever the model wrote", () => {
    expect(faultName("F06", "Prompt version regression")).toBe("Retrieval collapse");
    expect(faultName("F08", "config_regression")).toBe(
      "Configuration or environment regression",
    );
  });

  it("fall back to the stored wording for a class the catalogue does not list", () => {
    expect(faultName("F99", "made_up_fault")).toBe("made up fault");
    expect(faultName(null, null)).toBe("");
  });
});
