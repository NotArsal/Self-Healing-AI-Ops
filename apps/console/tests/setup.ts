/**
 * Test setup: jsdom gaps and a WebSocket double.
 *
 * jsdom has no WebSocket, so `useEvents` would throw on import. The double is
 * deliberately minimal and controllable — a test pushes a frame with
 * `lastSocket().receive(event)`, which is how the live-update tests prove the
 * timeline renders pushed events rather than polled ones.
 */

import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

export class FakeSocket {
  static instances: FakeSocket[] = [];

  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  readonly sent: string[] = [];
  closed = false;

  constructor(public url: string) {
    FakeSocket.instances.push(this);
    // Open on a microtask so a listener attached after construction still fires.
    queueMicrotask(() => this.onopen?.());
  }

  /** Push one server frame to this socket. */
  receive(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
    this.onclose?.();
  }
}

export const lastSocket = (): FakeSocket | undefined =>
  FakeSocket.instances.at(-1);

vi.stubGlobal("WebSocket", FakeSocket);

// matchMedia is used by the reduced-motion CSS only, but Next's dev overlay and
// some RTL helpers probe it.
vi.stubGlobal(
  "matchMedia",
  vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
);

// Everything below needs a DOM. The CSS-arithmetic suite runs under the node
// environment and shares this file, so each DOM shim is guarded rather than
// assumed — an unguarded `Element` reference here failed that whole suite at
// import time.
const hasDom = typeof window !== "undefined";

// jsdom does not implement scrollIntoView; the timeline and evidence list call it.
if (hasDom) {
  Element.prototype.scrollIntoView = vi.fn();
}

// Node 22 exposes its own `localStorage` global, which is NOT available without
// --localstorage-file, and it shadows the jsdom one. The result is
// `window.localStorage === undefined`, so the theme toggle has nothing to read.
// A Map-backed stand-in keeps the persistence test honest while leaving the
// component's own try/catch guards in place for the real browser cases.
if (hasDom && !window.localStorage) {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, String(value)),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
      key: (index: number) => [...store.keys()][index] ?? null,
      get length() {
        return store.size;
      },
    },
  });
}

afterEach(() => {
  FakeSocket.instances.length = 0;
  if (!hasDom) return;
  cleanup();
  document.documentElement.setAttribute("data-theme", "dark");
  window.localStorage?.clear();
});
