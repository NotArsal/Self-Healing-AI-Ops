/**
 * Distributed tracing configuration and deep-link generation.
 *
 * Configured via:
 *   NEXT_PUBLIC_KAVACH_JAEGER (default: http://localhost:16686)
 *   NEXT_PUBLIC_KAVACH_GRAFANA (default: http://localhost:3002)
 */

export const JAEGER_BASE =
  process.env.NEXT_PUBLIC_KAVACH_JAEGER ?? "http://localhost:16686";

export const GRAFANA_BASE =
  process.env.NEXT_PUBLIC_KAVACH_GRAFANA ?? "http://localhost:3002";

/** Jaeger deep-link shape filtered by `kavach.incident_id`. */
export const traceUrl = (incidentId: string): string =>
  `${JAEGER_BASE}/search?service=kavach-control-plane` +
  `&tags=${encodeURIComponent(JSON.stringify({ "kavach.incident_id": incidentId }))}`;
