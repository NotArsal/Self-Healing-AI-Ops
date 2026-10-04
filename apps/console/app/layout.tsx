import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";

// Both faces are self-hosted from npm, not fetched from a font CDN. The demo
// has to work offline (ROADMAP P8, "no network, local model only"), and a
// build-time webfont fetch is a network dependency in the build.
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kavach console",
  description: "Autonomous self-healing operations platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // Dark is the primary theme and renders first; the rail's toggle swaps the
    // attribute and persists the choice.
    <html lang="en" data-theme="dark" className={GeistSans.variable}>
      <body>{children}</body>
    </html>
  );
}
