/**
 * Base URL of the Kavach control plane.
 *
 * Port 8001, not 8000: another server on 8000 (a common default) can bind
 * 0.0.0.0 while Kavach binds 127.0.0.1, and `localhost` then resolves to the
 * wrong one over IPv6. The console silently talks to a different application
 * and every panel looks merely empty rather than misconfigured.
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8001";

export const apiUrl = (path: string): string =>
  `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
