import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Vitest for the console.
 *
 * `esbuild.jsx: "automatic"` is explicit on purpose: the app's tsconfig sets
 * `jsx: "preserve"` for Next's own compiler, and esbuild honours that, which
 * leaves raw JSX for a runtime that is not there. Next does not use this file,
 * so overriding it here affects tests only.
 */
export default defineConfig({
  esbuild: { jsx: "automatic", jsxImportSource: "react" },
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.tsx", "tests/**/*.test.ts"],
  },
});
