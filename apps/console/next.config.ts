import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev-tools badge sits bottom-left, exactly where the rail's mode
  // indicator lives, and obscures it during a demo. It is dev-only and never
  // in a production build, but the demo runs `next dev`.
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
