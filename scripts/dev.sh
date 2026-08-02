#!/usr/bin/env bash
# Runs the whole local stack (Postgres/Redis containers + API + Celery
# worker + frontend) from one terminal. Ctrl+C stops all three foreground
# processes together.
#
# The worker runs on the host (not in Docker) so it can reach Apple
# Silicon's MPS GPU -- see README's "Running" section for why.
set -euo pipefail
cd "$(dirname "$0")/.."

#: Not 3000. An unrelated nginx on this machine listens on 3000 and
#: proxy_passes to localhost:3000 (itself), with `root html;` as the
#: fallback -- so page HTML proxies through but /_next/static/* 404s.
#: The result is a page with no CSS and no hydration: unstyled, and every
#: button silently does nothing. Override with WEB_PORT=... if 3100 is
#: also taken.
WEB_PORT="${WEB_PORT:-3100}"

docker compose up -d postgres redis

( uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 | sed -u 's/^/[api]    /' ) &
( PYTORCH_ENABLE_MPS_FALLBACK=1 uv run celery -A app.workers.celery_app worker \
    --loglevel=info --pool=solo 2>&1 | sed -u 's/^/[worker] /' ) &
( cd frontend && npm run dev -- -p "$WEB_PORT" 2>&1 | sed -u 's/^/[web]    /' ) &

echo ""
echo "  ==> open http://localhost:${WEB_PORT}"
echo ""

cleanup() {
    # The pkill fallbacks catch processes that fork outside this script's
    # process group and would otherwise linger: celery's worker (the same
    # stray-process failure mode that causes "Received unregistered task"
    # errors on the next `make worker` start) and `uv run uvicorn --reload`,
    # whose reloader child ignores plain SIGTERM. kill 0 (everything still
    # in this group) runs before the final -9 sweep, but after it this
    # shell is dead too, so nothing after it executes -- the two -9 lines
    # below must come first, not after.
    pkill -f "celery -A app.workers.celery_app worker" 2>/dev/null || true
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 1
    pkill -9 -f "celery -A app.workers.celery_app worker" 2>/dev/null || true
    pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
    kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
