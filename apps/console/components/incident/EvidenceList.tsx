/**
 * Evidence items — DESIGN_SYSTEM.md §7.4.
 *
 * Collapsed: a one-line summary with a kind icon and a mono source reference.
 * Expanded: the payload in `--k-surface-sunken`, mono, horizontally scrollable,
 * never wrapped.
 *
 * Every item shows its stable `evidence_id`, and a diagnosis citation scrolls to
 * and opens the matching item in place. That link is the whole trust mechanism,
 * so it is visible rather than implied — and it resolves inside the console,
 * never to an external page.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { Icon, type IconName } from "../ui/Icon";
import type { EvidenceItem } from "@/lib/api";

const KIND_ICON: Record<string, IconName> = {
  metric: "activity",
  config: "cpu",
  verification: "check",
  health: "gauge",
  log: "list",
  baseline: "database",
  service: "cpu",
};

function Item({
  item,
  cited,
  open,
  onToggle,
}: {
  item: EvidenceItem;
  cited: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const row = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (open) row.current?.scrollIntoView({ block: "nearest" });
  }, [open]);

  return (
    <li
      ref={row}
      id={`evidence-${item.eid}`}
      style={{ borderBottom: "1px solid var(--k-border-subtle)" }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={`evidence-body-${item.eid}`}
        style={{
          display: "grid",
          gridTemplateColumns: "16px 64px 1fr 14px",
          gap: "var(--k-space-2)",
          alignItems: "center",
          width: "100%",
          minHeight: 40,
          padding: "6px 4px",
          textAlign: "left",
          background: "none",
          border: "none",
          borderLeft: cited
            ? "2px solid var(--k-state-diagnosing)"
            : "2px solid transparent",
        }}
      >
        <span className="k-faint" style={{ display: "flex" }}>
          <Icon name={KIND_ICON[item.kind] ?? "info"} />
        </span>
        <span className="k-mono-sm" style={{ color: "var(--k-text-muted)" }}>
          {item.eid}
        </span>
        <span className="k-sm" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {item.name.replace(/_/g, " ")}
          <span className="k-faint"> · {item.value}</span>
        </span>
        <span className="k-faint" style={{ display: "flex" }}>
          <Icon name={open ? "chevron-down" : "chevron-right"} />
        </span>
      </button>

      {open && (
        <dl
          id={`evidence-body-${item.eid}`}
          className="k-sunken k-mono"
          style={{
            margin: "0 4px 8px 22px",
            padding: "var(--k-space-3)",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "4px var(--k-space-3)",
            overflowX: "auto",
          }}
        >
          <dt className="k-faint">value</dt>
          <dd style={{ margin: 0, whiteSpace: "pre" }}>{item.value}</dd>
          <dt className="k-faint">kind</dt>
          <dd style={{ margin: 0 }}>{item.kind}</dd>
          {item.expected && (
            <>
              <dt className="k-faint">healthy</dt>
              <dd style={{ margin: 0, whiteSpace: "pre" }}>{item.expected}</dd>
            </>
          )}
          {item.note && (
            <>
              <dt className="k-faint">note</dt>
              <dd style={{ margin: 0, whiteSpace: "pre-wrap" }}>{item.note}</dd>
            </>
          )}
        </dl>
      )}
    </li>
  );
}

export function EvidenceList({
  items,
  citedIds,
  openId,
  onOpenChange,
}: {
  items: EvidenceItem[];
  citedIds: string[];
  openId: string;
  onOpenChange: (eid: string) => void;
}) {
  const [filterCited, setFilterCited] = useState(false);
  const cited = new Set(citedIds);
  const shown = filterCited ? items.filter((i) => cited.has(i.eid)) : items;

  return (
    <section aria-labelledby="evidence-heading">
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--k-space-2)",
          marginBottom: "var(--k-space-2)",
        }}
      >
        <h3 id="evidence-heading">Evidence ({items.length})</h3>
        {citedIds.length > 0 && (
          <button
            type="button"
            onClick={() => setFilterCited((on) => !on)}
            aria-pressed={filterCited}
            className="k-xs"
            style={{
              padding: "3px 8px",
              minHeight: 24,
              borderRadius: "var(--k-radius-sm)",
              border: "1px solid var(--k-border)",
              background: filterCited ? "var(--k-surface-raised)" : "transparent",
              color: "var(--k-text-muted)",
            }}
          >
            {filterCited ? "Showing cited only" : `Cited (${citedIds.length})`}
          </button>
        )}
      </header>

      {items.length === 0 ? (
        <p className="k-sm k-muted" style={{ margin: 0 }}>
          No evidence collected. The frame is built when RCA runs.
        </p>
      ) : (
        <ul
          className="k-scroll"
          style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 320 }}
        >
          {shown.map((item) => (
            <Item
              key={item.eid}
              item={item}
              cited={cited.has(item.eid)}
              open={openId === item.eid}
              onToggle={() => onOpenChange(openId === item.eid ? "" : item.eid)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
