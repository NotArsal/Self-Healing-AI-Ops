/**
 * The 64px left rail — DESIGN_SYSTEM.md §6.
 *
 * Navigation icons at the top, theme toggle and the mode indicator at the
 * bottom. The mode indicator must never scroll away (UX-01), so the rail is
 * fixed-height flex with the indicator pinned to the end.
 *
 * Icon-only navigation needs a real accessible name per target, hence the
 * `aria-label` plus `title` on each link; §10 requires 40x40 minimum targets.
 */

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon, type IconName } from "./Icon";
import { ModeIndicator } from "../safety/ModeIndicator";

const THEME_KEY = "kavach-theme";

/**
 * Theme preference is the one thing this console keeps in browser storage, and
 * every access is guarded: `localStorage` is absent or throws in a private
 * window, with site data blocked, and in some embedded views. The theme is a
 * per-viewer convenience, so losing it must not break the page — dark is the
 * primary theme and the correct fallback.
 */
const readTheme = (): "dark" | "light" | null => {
  try {
    const stored = window.localStorage?.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
};

const writeTheme = (value: "dark" | "light"): void => {
  try {
    window.localStorage?.setItem(THEME_KEY, value);
  } catch {
    // Preference is not persisted. The theme still applies for this session.
  }
};

function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = readTheme();
    if (stored) {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    }
  }, []);

  const toggle = (): void => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    writeTheme(next);
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      style={{
        display: "grid",
        placeItems: "center",
        width: 40,
        height: 40,
        borderRadius: "var(--k-radius-sm)",
        border: "1px solid var(--k-border)",
        background: "transparent",
        color: "var(--k-text-muted)",
      }}
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
    </button>
  );
}

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Operations", icon: "activity" },
  { href: "/preflight", label: "Onboarding and preflight", icon: "list" },
  { href: "/observability", label: "Observability", icon: "gauge" },
  { href: "/logs", label: "Logs", icon: "terminal" },
  { href: "/traces", label: "Traces", icon: "git-commit" },
];

export function Rail({
  mode,
  modeEnforced,
  current,
}: {
  mode: string;
  modeEnforced: boolean;
  current: string;
}) {
  return (
    <nav
      aria-label="Primary"
      style={{
        width: "var(--k-rail)",
        flex: "0 0 var(--k-rail)",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "var(--k-space-2)",
        padding: "var(--k-space-3) 0",
        background: "var(--k-surface)",
        borderRight: "1px solid var(--k-border)",
      }}
    >
      <span
        aria-hidden="true"
        title="Kavach"
        style={{
          width: 28,
          height: 28,
          borderRadius: "var(--k-radius-sm)",
          background: "var(--k-loop-gradient)",
          marginBottom: "var(--k-space-2)",
        }}
      />

      {NAV.map((item) => {
        const active = item.href === current;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-label={item.label}
            title={item.label}
            aria-current={active ? "page" : undefined}
            style={{
              display: "grid",
              placeItems: "center",
              width: 40,
              height: 40,
              borderRadius: "var(--k-radius-sm)",
              border: `1px solid ${active ? "var(--k-border-strong)" : "transparent"}`,
              background: active ? "var(--k-surface-raised)" : "transparent",
              color: active ? "var(--k-text)" : "var(--k-text-muted)",
            }}
          >
            <Icon name={item.icon} size={16} />
          </Link>
        );
      })}

      <span style={{ flex: 1 }} />
      <ThemeToggle />
      <ModeIndicator mode={mode} enforced={modeEnforced} />
    </nav>
  );
}
