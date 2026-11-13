/**
 * The observability page was split into History, Logs, Metrics and Traces
 * (ADR 0029). Old links land on Metrics, which holds most of what was here.
 */

import { redirect } from "next/navigation";

export default function ObservabilityPage(): never {
  redirect("/metrics");
}
