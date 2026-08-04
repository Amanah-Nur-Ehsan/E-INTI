# Production build for the Next.js frontend. NOT used for local dev
# (`make dev` runs `next dev` directly on the host) -- this is for
# deploying behind a reverse proxy (e.g. Nginx Proxy Manager).
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `next build` resolves next.config.ts's rewrites() destination once and
# writes it verbatim into .next/routes-manifest.json -- `next start` reads
# that manifest, it does NOT re-invoke rewrites() or re-read process.env at
# boot. So API_ORIGIN must be a build ARG, not a docker-compose `environment:`
# entry (confirmed by inspecting the built manifest: a runtime-only env var
# here produced a container that could reach its own value via `printenv`
# but still proxied to the stale build-time default, ECONNREFUSED).
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=$API_ORIGIN
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3100
CMD ["npm", "run", "start", "--", "-p", "3100"]
