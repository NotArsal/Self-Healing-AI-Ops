/**
 * The icon set. Inline stroke SVG, sized by prop, `currentColor` throughout.
 *
 * It exists because DESIGN_SYSTEM.md §10 requires that every state, risk tier
 * and probe result carry an icon as well as a colour — a reviewer with
 * deuteranopia must be able to read the console, and a projector washes out
 * greens regardless. §11 forbids emoji as status icons, so these are drawn.
 *
 * `aria-hidden` on every glyph: the adjacent text label is the accessible
 * name, so announcing the icon too would just duplicate it.
 */

export type IconName =
  | "check"
  | "cross"
  | "pending"
  | "shield"
  | "shield-alert"
  | "shield-x"
  | "ban"
  | "info"
  | "chevron-right"
  | "chevron-down"
  | "activity"
  | "database"
  | "cpu"
  | "gauge"
  | "list"
  | "sun"
  | "moon";

const PATHS: Record<IconName, React.ReactNode> = {
  check: <polyline points="3.5 8.5 6.5 11.5 12.5 4.5" />,
  cross: (
    <>
      <line x1="4" y1="4" x2="12" y2="12" />
      <line x1="12" y1="4" x2="4" y2="12" />
    </>
  ),
  pending: <circle cx="8" cy="8" r="4.5" />,
  shield: <path d="M8 2 13 4v4c0 3-2.2 5.3-5 6-2.8-.7-5-3-5-6V4z" />,
  "shield-alert": (
    <>
      <path d="M8 2 13 4v4c0 3-2.2 5.3-5 6-2.8-.7-5-3-5-6V4z" />
      <line x1="8" y1="5.5" x2="8" y2="9" />
      <line x1="8" y1="11" x2="8" y2="11.2" />
    </>
  ),
  "shield-x": (
    <>
      <path d="M8 2 13 4v4c0 3-2.2 5.3-5 6-2.8-.7-5-3-5-6V4z" />
      <line x1="6" y1="6" x2="10" y2="10" />
      <line x1="10" y1="6" x2="6" y2="10" />
    </>
  ),
  ban: (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <line x1="4.2" y1="11.8" x2="11.8" y2="4.2" />
    </>
  ),
  info: (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <line x1="8" y1="7.5" x2="8" y2="11" />
      <line x1="8" y1="5" x2="8" y2="5.2" />
    </>
  ),
  "chevron-right": <polyline points="6 4 10 8 6 12" />,
  "chevron-down": <polyline points="4 6 8 10 12 6" />,
  activity: <polyline points="1.5 8 5 8 7 3.5 9.5 12.5 11.5 8 14.5 8" />,
  database: (
    <>
      <ellipse cx="8" cy="4" rx="5" ry="2" />
      <path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4" />
      <path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" />
    </>
  ),
  cpu: (
    <>
      <rect x="4" y="4" width="8" height="8" rx="1" />
      <line x1="8" y1="1.5" x2="8" y2="4" />
      <line x1="8" y1="12" x2="8" y2="14.5" />
      <line x1="1.5" y1="8" x2="4" y2="8" />
      <line x1="12" y1="8" x2="14.5" y2="8" />
    </>
  ),
  gauge: (
    <>
      <path d="M2.5 11a5.5 5.5 0 1 1 11 0" />
      <line x1="8" y1="11" x2="10.5" y2="6.5" />
    </>
  ),
  list: (
    <>
      <line x1="5" y1="4.5" x2="13" y2="4.5" />
      <line x1="5" y1="8" x2="13" y2="8" />
      <line x1="5" y1="11.5" x2="13" y2="11.5" />
      <line x1="2.5" y1="4.5" x2="2.7" y2="4.5" />
      <line x1="2.5" y1="8" x2="2.7" y2="8" />
      <line x1="2.5" y1="11.5" x2="2.7" y2="11.5" />
    </>
  ),
  sun: (
    <>
      <circle cx="8" cy="8" r="3" />
      <line x1="8" y1="1.5" x2="8" y2="3" />
      <line x1="8" y1="13" x2="8" y2="14.5" />
      <line x1="1.5" y1="8" x2="3" y2="8" />
      <line x1="13" y1="8" x2="14.5" y2="8" />
    </>
  ),
  moon: <path d="M12.5 10.2A5.5 5.5 0 0 1 6 3.6a5.5 5.5 0 1 0 6.5 6.6z" />,
};

export function Icon({
  name,
  size = 14,
  strokeWidth = 1.6,
}: {
  name: IconName;
  size?: number;
  strokeWidth?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flex: "0 0 auto" }}
    >
      {PATHS[name]}
    </svg>
  );
}
