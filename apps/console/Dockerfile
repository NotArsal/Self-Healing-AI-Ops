# The console, as a production build (ADR 0017).
#
# Until 2026-10-19 the console was the one part of Kavach that `make up` did
# not start. It ran through `make dev-console` -> `next dev` in a terminal
# somebody had to remember to open, which made the best-looking surface in the
# system the most likely thing to be missing at the start of a demo - and a
# development server at that, with on-demand compilation on first paint.
#
# NEXT_PUBLIC_* IS BAKED AT BUILD TIME, NOT READ AT RUNTIME.
# `lib/api.ts` reads `process.env.NEXT_PUBLIC_KAVACH_API`, and Next inlines
# that value into the client bundle during `next build`. Passing it as a
# compose `environment:` entry would do nothing at all - the container would
# start, the page would load, and every request would go to the baked default
# with no error anywhere. It is an ARG for that reason.
#
# The value is a HOST url, not a service name: this variable is read by the
# browser, which is not on the compose network. `http://api:8000` would
# resolve inside the container and nowhere the user is sitting.

FROM node:22-alpine AS deps
WORKDIR /app
# corepack ships with node. WITHOUT a `packageManager` field it resolves
# "latest" over the network on every build - an extra round trip that is
# nondeterministic and that timed out on 2026-10-19, failing the build for
# a reason that had nothing to do with the code. package.json pins
# pnpm@12.4.1, so this fetches one exact version.
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_KAVACH_API=http://localhost:8080
ENV NEXT_PUBLIC_KAVACH_API=$NEXT_PUBLIC_KAVACH_API
ARG NEXT_PUBLIC_KAVACH_JAEGER=http://localhost:16686
ENV NEXT_PUBLIC_KAVACH_JAEGER=$NEXT_PUBLIC_KAVACH_JAEGER
ARG NEXT_PUBLIC_KAVACH_GRAFANA=http://localhost:3002
ENV NEXT_PUBLIC_KAVACH_GRAFANA=$NEXT_PUBLIC_KAVACH_GRAFANA
ENV NEXT_TELEMETRY_DISABLED=1
# `next.config.ts` keeps `ignoreBuildErrors: false` and
# `eslint.ignoreDuringBuilds: false`, so a type error in the console fails this
# build rather than shipping. That is the same gate `make check` applies and it
# is deliberately not relaxed for the image.
RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Not root. The console reads one HTTP API and serves static files; it has no
# reason to hold any privilege, and the demo machine runs it next to a
# container that genuinely does hold the Docker socket.
RUN addgroup -g 1001 -S nodejs && adduser -S -u 1001 -G nodejs nextjs

# `output: "standalone"` emits a self-contained server plus only the
# node_modules it actually traced, which is why the whole dependency tree above
# does not ship. Static assets and the public dir are NOT included in it and
# have to be copied next to it.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
