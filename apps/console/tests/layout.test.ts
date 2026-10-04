/**
 * The projector constraint, as arithmetic.
 *
 * UX-06 requires the console to be legible at 1280x720. That is a visual
 * claim, but the part that silently breaks it is not visual: it is the sum of
 * the fixed column widths, the rail, the gaps and the padding exceeding the
 * viewport, which turns into horizontal page scroll.
 *
 * This caught a real defect — a 300px health column with a
 * `minmax(480px, 1fr)` centre needed 1288px — so it stays as a guard. A
 * screenshot would not have failed CI; this does.
 */

// @vitest-environment node

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// Resolved from the vitest root (apps/console) rather than `import.meta.url`,
// which is not a file URL once vite has transformed the module.
const css = readFileSync(resolve("app/globals.css"), "utf8");

const RAIL = 64;
const SPACE = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48, 8: 64 } as const;

/** Pull `grid-template-columns`, `gap` and `padding` out of a `.k-zones` block. */
function zones(blockMatcher: RegExp): {
  columns: string;
  gap: number;
  padding: number;
} {
  const block = css.match(blockMatcher);
  if (!block?.[0]) throw new Error(`no .k-zones block for ${blockMatcher}`);
  const body = block[0];

  const columns = /grid-template-columns:\s*([^;]+);/.exec(body)?.[1]?.trim();
  if (!columns) throw new Error("no grid-template-columns");

  const step = (property: string, fallback: number): number => {
    const found = new RegExp(`${property}:\s*var\(--k-space-(\d)\)`).exec(body);
    return found?.[1] ? SPACE[Number(found[1]) as keyof typeof SPACE] : fallback;
  };

  return { columns, gap: step("gap", 16), padding: step("padding", 16) };
}

const px = (value: string): number => Number(/^(\d+)px$/.exec(value.trim())?.[1] ?? 0);

describe("1280x720 projector constraint", () => {
  it("fits the default three-zone layout inside 1280px", () => {
    const { columns, gap, padding } = zones(/\.k-zones \{[^}]+\}/);
    const [left, centre, right] = columns.split(" ").reduce<string[]>(
      (parts, token) => {
        // `minmax(0,` and `1fr)` arrive as separate tokens.
        if (token.startsWith("minmax(")) parts.push("minmax");
        else if (!token.includes("fr)")) parts.push(token);
        return parts;
      },
      [],
    );

    expect(centre).toBe("minmax");
    const fixed = px(left ?? "") + px(right ?? "");
    const required = RAIL + padding * 2 + gap * 2 + fixed;

    // The centre column must still have usable room, not merely not overflow.
    expect(required).toBeLessThan(1280);
    expect(1280 - required).toBeGreaterThanOrEqual(480);
  });

  it("uses minmax(0, 1fr) for the centre, never a px floor", () => {
    // A `minmax(480px, 1fr)` centre cannot shrink, so an over-wide row
    // overflows the viewport instead of narrowing. That was the actual bug.
    expect(css).toMatch(/\.k-zones \{[^}]*minmax\(0,\s*1fr\)/);
    expect(css).not.toMatch(/grid-template-columns:[^;]*minmax\(\s*\d+px/);
  });

  it("narrows rather than overflows below 1280", () => {
    const { columns, gap, padding } = zones(
      /@media \(max-width: 1279px\) \{\s*\.k-zones \{[^}]+\}/,
    );
    const fixed = columns
      .split(" ")
      .filter((t) => /^\d+px$/.test(t))
      .reduce((sum, t) => sum + px(t), 0);
    expect(RAIL + padding * 2 + gap * 2 + fixed).toBeLessThan(1024);
  });

  it("declares every breakpoint the design system names", () => {
    for (const bp of ["1600px", "1279px", "1023px"]) {
      expect(css).toContain(bp);
    }
  });

  it("gives the page an explicit background, so no theme shows white", () => {
    expect(css).toMatch(/body \{[^}]*background:\s*var\(--k-bg\)/);
  });

  it("defines every token in both themes", () => {
    const dark = css.slice(css.indexOf('data-theme="dark"'), css.indexOf('data-theme="light"'));
    const light = css.slice(css.indexOf('data-theme="light"'));
    const names = (block: string): Set<string> =>
      new Set([...block.matchAll(/(--k-[a-z0-9-]+):/g)].map((m) => m[1] as string));

    const darkNames = names(dark);
    const lightNames = names(light.slice(0, light.indexOf("}")));
    // Light remaps the same names; it must not invent new ones (§2.6).
    for (const name of lightNames) expect(darkNames).toContain(name);
  });

  it("never removes the focus ring", () => {
    expect(css).toMatch(/:focus-visible \{[^}]*outline:\s*2px solid/);
    expect(css).not.toMatch(/outline:\s*(none|0)\s*;/);
  });

  it("honours prefers-reduced-motion", () => {
    expect(css).toContain("prefers-reduced-motion: reduce");
  });
});
