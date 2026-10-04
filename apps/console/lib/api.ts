/**
 * The typed API client.
 *
 * Every request shape and response shape comes from `lib/api/generated/schema.d.ts`,
 * which `make gen-client` regenerates from the control plane's OpenAPI document.
 * Nothing here describes a backend contract — `openapi-fetch` is a generic
 * library over the generated types, so a field that changes server-side breaks
 * `tsc` instead of breaking silently at runtime.
 *
 * Do not add a hand-written wrapper per endpoint here. If a call needs a new
 * shape, the shape belongs in the backend's Pydantic model.
 */

import createClient from "openapi-fetch";

import type { components, paths } from "./api/generated/schema";

export const API_BASE =
  process.env.NEXT_PUBLIC_KAVACH_API ?? "http://localhost:8080";

export const api = createClient<paths>({ baseUrl: API_BASE });

export type System = components["schemas"]["SystemOut"];
export type Dependency = components["schemas"]["Dependency"];
export type IncidentSummary = components["schemas"]["IncidentSummary"];
export type Incident = components["schemas"]["IncidentOut"];

// Derived from IncidentOut rather than named separately. The generator emits
// the nested objects inline, so `components["schemas"]["RcaOut"]` and
// `IncidentOut["rca"]` are structurally identical but nominally distinct, and
// a component typed against the wrong one will not accept the other.
export type Rca = NonNullable<Incident["rca"]>;
export type Action = NonNullable<Incident["action"]>;
export type Verification = NonNullable<Incident["verification"]>;
export type Detection = NonNullable<Incident["detection"]>;
export type Diagnosis = NonNullable<Rca["diagnosis"]>;
export type Validation = NonNullable<Rca["validation"]>;
export type EvidenceItem = NonNullable<Rca["evidence"]>[number];
export type LoopEvent = components["schemas"]["EventOut"];
export type Preflight = components["schemas"]["PreflightOut"];
export type PreflightCheck = components["schemas"]["PreflightCheckOut"];
export type Mode = System["mode"];

/** The live event socket. Derived from API_BASE so there is one place to point. */
export const wsUrl = (): string =>
  `${API_BASE.replace(/^http/, "ws")}/v1/ws`;
