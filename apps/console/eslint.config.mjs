import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    // All generated, none of it authored here: `.next/` is the build,
    // `lib/api/generated/` is the OpenAPI client, and `next-env.d.ts` is
    // written by Next on every build (and gitignored). Linting generated files
    // fails the gate on style Next itself chose.
    ignores: [
      ".next/**",
      "node_modules/**",
      "lib/api/generated/**",
      "next-env.d.ts",
    ],
  },
];

export default config;
