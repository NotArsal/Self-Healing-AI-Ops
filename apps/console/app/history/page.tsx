/**
 * History — every stored incident (ADR 0029).
 *
 * It sat under the incident stream on the operations screen, 3654px down a
 * 210px box, repeating the 50 incidents the stream already listed. Here it is
 * the whole page, reads up to 1000 rows from the store, and each ID opens
 * that incident on the operations screen.
 */

"use client";

import { HistoryTable } from "@/components/incident/IncidentStream";
import { Empty, Page, Unreachable, UNREACHABLE } from "@/components/ui/Page";
import { api } from "@/lib/api";
import { usePolled, useSystem } from "@/lib/live";

const LIMIT = 1000;
const loadAll = () => api.GET("/v1/incidents", { params: { query: { limit: LIMIT } } });

export default function HistoryPage() {
  const { system } = useSystem();
  const { data: incidents, failed } = usePolled(loadAll, 15_000);

  return (
    <Page
      system={system}
      current="/history"
      title="History"
      intro="Every incident in the store, newest first. Open one to see its evidence, diagnosis, plan and verification on the operations screen."
    >
      <Unreachable message={failed ? UNREACHABLE : ""} />
      {incidents === null ? (
        // §8 Loading: a skeleton block, never a spinner.
        <div
          data-testid="history-skeleton"
          style={{
            height: 160,
            maxWidth: 1040,
            borderRadius: "var(--k-radius-sm)",
            background: "var(--k-surface-raised)",
          }}
        />
      ) : incidents.length === 0 ? (
        <Empty>No incidents yet. Start a run from the operations screen.</Empty>
      ) : (
        <div style={{ maxWidth: 1040 }}>
          <HistoryTable
            incidents={incidents}
            title={`${incidents.length}${incidents.length === LIMIT ? "+" : ""} incidents`}
            linkIds
          />
        </div>
      )}
    </Page>
  );
}
