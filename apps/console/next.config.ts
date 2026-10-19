import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server plus only the node_modules Next traced, so the
  // image ships megabytes instead of the whole dependency tree. Required by
  // `Dockerfile`, which copies `.next/standalone` (ADR 0017).
  output: "standalone",
  // The dev-tools badge sits bottom-left, exactly where the rail's mode
  // indicator lives, and obscures it during a demo. It is dev-only and never
  // in a production build - which, since 2026-10-19, is what the demo runs.
  // Kept because `make dev-console` is still how the console is developed.
  devIndicators: false,
  reactStrictMode: true,
  typescript: {
    // A backend type change must break this build (AGENTS.md, TypeScript rules).
    ignoreBuildErrors: false,
  },
  eslint: {
    ignoreDuringBuilds: false,
  },
};

export default nextConfig;
