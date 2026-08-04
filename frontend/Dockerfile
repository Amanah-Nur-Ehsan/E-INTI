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
# API_ORIGIN is read at request time by next.config.ts's rewrite (server-side,
# inside the container), not baked in at build time -- no build ARG needed.
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
