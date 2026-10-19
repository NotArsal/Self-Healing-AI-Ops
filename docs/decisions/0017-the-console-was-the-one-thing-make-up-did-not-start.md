# ADR 0017 — The console was the one thing `make up` did not start

**Date:** 2026-10-19
**Status:** Accepted
**Changes:** new `apps/console/Dockerfile` and `.dockerignore`;
`output: "standalone"` in `next.config.ts`; new `console` service in
`infra/docker-compose.yml`.
**Related:** [ADR 0016](0016-the-control-plane-had-no-telemetry-of-its-own.md)

## Context

Every other component of Kavach came up with one `make up`. The console did
not. It ran through `make dev-console` → `pnpm dev` → `next dev -p 3001`, in a
terminal somebody had to remember to open.

Two problems with that, and the second is the real one:

1. **It was a development server.** On-demand compilation, slower first paint,
   and the dev-tools badge that `devIndicators: false` exists to hide — a
   setting whose comment said, in as many words, *"the demo runs `next dev`"*.
2. **It was the surface the demo spends most of its time pointed at.** 6,631
   lines, 17 components, its own design system, 71 of the 79 frontend tests.
   The best-looking thing in the system was the only one not wired into the
   one-command start, and therefore the most likely to be missing when it
   mattered.

A demo where four services start automatically and the fifth needs a
remembered incantation is a demo with a single point of human failure in it,
sitting at the beginning.

## Decision

**Ship the console as a built image, started by compose like everything else.
Keep `make dev-console` for developing it.**

`next build` with `output: "standalone"`, served by `node server.js`. The
image is **323MB**, smaller than the API's 387MB, because standalone emits
only the `node_modules` Next actually traced rather than the full dependency
tree.

Three details worth recording, because each is a trap:

### `NEXT_PUBLIC_*` is baked at build time, not read at runtime

`lib/api.ts` reads `process.env.NEXT_PUBLIC_KAVACH_API`, and Next inlines that
into the **client** bundle during `next build`. Passing it as a compose
`environment:` entry would do nothing whatsoever — the container would start,
the page would load, and every request would go to the compiled-in default
with no error anywhere to say why. It is a build `ARG`.

### The value is a host URL, not a service name

The variable is read by the browser, which is not on the compose network.
`http://api:8000` resolves inside the container and nowhere the user is
sitting. It is `http://localhost:${API_PORT:-8080}`, tied to the port the
`api` service publishes.

### The published port stays 3001

Not because 3001 is special, but because `KAVACH_CONSOLE_ORIGIN` is
`http://localhost:3001` and the API's CORS allow-list reads it. Moving the
console would have silently broken every browser request with a CORS error
that looks like a backend fault. The target's own UI owns 3000.

## What is deliberately kept

`make dev-console` still exists and is still the right tool for *working on*
the console: hot reload, no rebuild. The compose service is for *running* it.
`devIndicators: false` stays for the same reason — the badge is dev-only, and
dev is still where the console is developed.

The build does not relax the gate: `ignoreBuildErrors: false` and
`eslint.ignoreDuringBuilds: false` are untouched, so a type error fails the
image build exactly as it fails `make check`.

### The healthcheck must not say `localhost`

It did, and the container reported **unhealthy for 16 consecutive checks**
while serving every request on its published port perfectly. Alpine's
`/etc/hosts` maps `localhost` to `::1` as well as `127.0.0.1`, busybox wget
tries IPv6 first, and the Next server binds `0.0.0.0:3000` — IPv4 only. The
other services use `localhost` safely because their base images carry no
`::1` entry, so the idiom copied from them was wrong in a way nothing else
in the file could reveal.

Left unfixed it would have been worse than cosmetic: anything declaring
`depends_on: console: condition: service_healthy` would wait forever on a
container that was working.

## Verification

Built, started and loaded at `http://localhost:3001` with the API reached at
the baked URL: dependencies 8/8 ok, live event stream, incident history. The
browser really did call the API, which is the one thing a `curl` of the page
cannot tell you and the one thing the `NEXT_PUBLIC_` trap above would have
broken.

## Lesson

Smaller than ADR 0014's, and the same family:

> **The component with no automation around it is the component nobody
> notices is missing, right up until it is.**

Everything that starts itself gets exercised every single day. The one thing
that needs a human to remember it gets exercised only when someone remembers
— which, on the day it matters most, is the day with the most to remember.
