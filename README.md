# CitationINTI

Backend for a Scopus reference citation recommender. A researcher uploads a draft
paper and a spreadsheet of Scopus-indexed candidate references; the system finds the
sentences that make citable claims and recommends references **from that uploaded
dataset only**, each with a percentage score and an LLM-verified support verdict.

This repository covers the full MVP: infrastructure, dataset import and enrichment,
draft parsing and claim detection, the recommendation engine, DOCX export with
tracked changes, and the Next.js review UI.

## How the pipeline works

```
import dataset ──► enrich (Scopus → Semantic Scholar → Crossref)
                        │
                        ▼
                   embed with SPECTER2 ──► pgvector
                        │
upload draft ──► parse + segment ──► detect claims (rules + Tier-1 LLM)
                        │
                        ▼
   per claim: pgvector top-20 ──► hybrid pre-rank top-10 ──► cross-encoder rerank
                                        │
                                        ▼
                          Tier-2 LLM verification (cached) ──► score ──► top-5
```

Every stage is idempotent and skips work already done, so re-running an analysis
after adding references only processes what changed.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker (for PostgreSQL + pgvector and Redis)
- macOS on Apple Silicon or Linux. Apple Silicon uses the MPS GPU automatically.

## Setup

```bash
uv sync
cp .env.example .env
docker compose up -d postgres redis
make db-upgrade
make models          # downloads spaCy, SPECTER2, and the cross-encoder
```

The Postgres container publishes **port 5433** on the host, because 5432 is
commonly already taken by a local PostgreSQL install. Adjust `docker-compose.yml`
and `DATABASE_URL` together if you want a different port.

Both Postgres and Redis are bound to `127.0.0.1` only — they are never reachable
from outside the host, deployed or not. Redis additionally requires a password
(`REDIS_PASSWORD`, default `devredispass` in `.env.example`); change it before any
non-local deployment. `MAX_UPLOAD_MB` (default 25) caps draft and dataset uploads.
`API_KEY` is an optional seam for a future auth layer — leave it empty for local
dev; once set, every request must carry a matching `X-API-Key` header on routes
that opt into `app.core.security.require_api_key`.

There is **no per-user authentication or authorization yet** — every endpoint is
open, and `projects` has no owner column. This is a deliberate MVP scope (the
product spec explicitly excludes multi-user auth), not an oversight, but it means
this API must not be exposed to untrusted networks as-is.

## Running

```bash
make dev       # containers + API + worker + frontend, one terminal, Ctrl+C stops all
```

Then open **http://localhost:3100**.

Or run each piece in its own terminal:

```bash
make api       # FastAPI on http://localhost:8000 (docs at /docs)
make worker    # Celery worker — run this on the host, not in Docker
```

The worker must run on the host: Docker Desktop cannot reach the Apple Silicon
GPU, so a containerised worker silently falls back to CPU and runs several times
slower. It uses `--pool=solo` because forking a process that has already
initialised MPS is crash-prone.

```bash
make web       # Next.js on http://localhost:3100, proxying /api/* to the backend
```

**The frontend deliberately does not use port 3000.** A common source of
confusion: if something else on the machine (an nginx, another dev server)
already holds 3000, Next.js still starts, but page HTML gets served while
`/_next/static/*` 404s — the page renders completely unstyled and no button
works, because React never hydrates. Port 3100 sidesteps it; override with
`WEB_PORT=3200 make dev` if 3100 is taken too.

The frontend is a separate `npm` project in `frontend/` — for local dev it runs on
the host with no Docker container, since the API and worker already run on the host
for MPS and a Node container would just add a container-to-host networking hop for
nothing. (A server deployment does containerize it — see "Server deployment" below;
that constraint is Mac-specific and doesn't apply to a Linux server.) Its typed API client
is generated from the running backend's OpenAPI schema (`lib/api/schema.d.ts`,
checked into git) via `make gen-api`; regenerate it whenever the API shape changes.

The review screen renders the draft **read-only** — the user accepts or rejects
suggestions, they never edit prose. A rich-text editor was deliberately not used:
`char_start`/`char_end` offsets are not meaningful inside a ProseMirror/Lexical
document model, and the moment the user could type, every stored offset would go
stale and silently fail export's `POSITION_MISMATCH` check. Highlights and ghost
text are computed by two pure functions (`lib/review/segments.ts`,
`lib/review/highlight.ts`) over plain `raw_text` and the claim list instead.

## Server deployment (Docker)

`make dev` (above) is for local Mac dev only — it deliberately runs the API,
worker, and frontend on the host, not in Docker, because local models need
Apple Silicon's MPS GPU, which Docker on macOS can't pass through. A Linux
server has no such constraint, so a server deploy containerizes everything
instead, behind whatever reverse proxy you use (Nginx Proxy Manager, Caddy,
etc.) for your domain/TLS.

```bash
cp .env.example .env    # then fill in real values -- .env is gitignored,
                         # it never travels with git and must be created
                         # by hand on every machine that needs it
docker compose --profile full up -d --build
```

This starts, in order: `postgres` + `redis`, a one-shot `migrate` service
(`alembic upgrade head`, then exits), then `api`, `worker`, and `web` once
their dependencies are healthy. `api`/`worker` share one image (`Dockerfile`
at the repo root) that bakes spaCy + SPECTER2 + the cross-encoder in at
*build* time via `scripts/warmup_models.py` — the containers need no network
access for models at runtime and don't lose the cache on every restart.
`web` is a separate multi-stage build (`frontend/Dockerfile`) that runs
`next build` then `next start`, with `API_ORIGIN=http://api:8000` passed
as a Docker **build arg** (`docker-compose.yml`'s `build.args`, not
`environment:`) so its same-origin `/api/*` rewrite reaches the API over
the Docker network. This has to be a build arg, not a runtime env var:
`next build` resolves `next.config.ts`'s `rewrites()` destination once and
writes it into `.next/routes-manifest.json`, which `next start` reads
verbatim — it does not re-invoke `rewrites()` or re-read `process.env` at
boot, confirmed by inspecting the built manifest directly. A container that
only had `API_ORIGIN` set at `docker run` time (correctly, verified with
`printenv` inside the container) still proxied to the stale build-time
default and failed with `ECONNREFUSED 127.0.0.1:8000` — this was a real
bug shipped and caught live on an actual deploy, not a hypothetical.

`worker` runs `--pool=threads --concurrency=2` (not `--pool=solo`, unlike
`make dev`'s local Mac worker): threads share one process, so there's one
copy of SPECTER2 + the cross-encoder in memory rather than two, and it puts
`app/core/device.py`'s CPU-limiting semaphore in the same process as the
models it serializes. Two concurrent analyses' Tier-1/Tier-2 LLM calls also
run in a per-analysis thread pool (`settings.llm_max_concurrency`) rather
than one call at a time — the actual wall-clock win, since almost all of a
draft's runtime used to be the *sum* of every LLM call's latency.

Local-model CPU is capped independently of that concurrency, for shared
boxes running other services alongside this one:
`settings.torch_num_threads` (default 1) bounds torch's own thread count,
and `device.local_inference()` is a process-wide semaphore held per *batch*
(not per whole-draft call) so two analyses' embedding/reranking never run
at the same instant — peak local-model CPU stays near `torch_num_threads`
cores regardless of how many analyses are queued. Raise it if the box has
CPU to spare; the tradeoff is faster embedding/reranking for a higher peak.

`settings.retrieve_claim_limit` (default 40, `0` = uncapped) is a separate,
larger lever: it caps how many of a draft's claims enter retrieval
(embedding + reranking) at all, picked by `Claim.claim_confidence` — a real
paper can have ~137 citation-worthy claims and only ever surface a 5-item
shortlist, so retrieval used to spend ~137 embeddings and ~1,370
cross-encoder pairs to use maybe 20 of them.

The `worker` command also passes `--beat --schedule=/tmp/celerybeat-schedule`,
embedding Celery's scheduler in the same process rather than a separate
container (safe only because there is exactly one worker — normally
discouraged with more than one, since each would fire the schedule
independently). It fires `library.refresh` every
`settings.library_beat_interval_seconds` (default 600s), which is how
enrichment/embedding of the shared reference library starts automatically
once the system is idle rather than needing a manual `POST
/library/refresh`. That task never competes with an in-flight analysis for
the worker's two thread slots: each tick checks for any `PENDING`/`RUNNING`
`AnalysisRun` first and, if one exists, does no work and reschedules itself
after `settings.library_idle_retry_seconds` instead — Celery/Redis have no
task-preemption primitive, so priority here means "refuse to start", not
"interrupt what's running". When idle, it processes at most
`settings.library_chunk_size` (default 25) rows per tick and re-queues
itself immediately if that chunk came back full, so a large backlog is
drained in short bursts rather than one long run that would itself block
the next paper upload. A short Redis lock (`library_refresh_lock`) guards
against two ticks overlapping.

Everything under this profile stays off `make dev`'s path entirely — a plain
`docker compose up -d postgres redis` (what `make dev` runs) never touches
`migrate`/`api`/`worker`/`web`, so the two workflows can't collide.

`postgres`/`redis`/`api`/`web` all publish to `127.0.0.1` only, matching this
file's existing loopback-only convention — nothing here is meant to be
reachable directly from the public internet.

If your reverse proxy runs directly on the host (not in Docker), point its
upstream at `http://127.0.0.1:3100`. If it's itself a Docker container (e.g.
Nginx Proxy Manager, its own separate Compose project), it can't reach that
loopback-only publish at all — Docker's `127.0.0.1:host:container` binding
only works for processes on the host itself, not for other containers, even
on the same machine. `web` already joins an external network named by
`NPM_NETWORK_NAME` (defaults to `nginx_proxy_manager_default`; check yours
with `docker network ls` — Compose auto-names it `<project-dir>_default`) so
this works automatically: point the proxy host's upstream at
`http://web:3100`, no manual `docker network connect` needed, and it survives
NPM's container being recreated. Override the default with
`NPM_NETWORK_NAME=your_actual_network_name` in `.env` if your reverse proxy's
Compose project isn't named `nginx_proxy_manager`.

Two things worth doing before this is exposed to real users, neither done
here since they're deployment-specific decisions, not defaults:
- **Auth is not actually wired up yet.** `require_api_key` exists
  (`app/core/security.py`) and reads `API_KEY` from `.env`, but no router
  currently depends on it -- setting `API_KEY` alone does nothing right now.
  Someone needs to add `dependencies=[Depends(require_api_key)]` to the
  routers that should require it before this is safe to expose beyond a
  reverse-proxy-level restriction (IP allowlist, HTTP basic auth in NPM, etc.).
- **Update `CORS_ORIGINS`** in `.env` to your actual domain. The browser
  never needs this for normal use (the frontend's `/api/*` rewrite keeps
  requests same-origin), but it matters the moment anything calls the API
  directly cross-origin.

Useful commands once it's up:
```bash
docker compose --profile full logs -f api worker web   # tail all three
docker compose --profile full ps                       # health status
docker compose --profile full down                     # stop (data persists in named volumes)
```

`pyproject.toml`'s `[tool.uv.sources]` pins `torch` to PyTorch's CPU-only
wheel index on Linux only (`sys_platform == 'linux'` marker) -- this image
never has a GPU, and the default CUDA-enabled wheel was pulling in the
entire `nvidia-cu12` runtime for nothing. Verified with `torch.__version__`
inside the built container (`2.x+cpu`, not the CUDA build) and a real
SPECTER2 embedding call on CPU. Took the api/worker image from ~7GB to
~2.9GB. macOS is untouched by the marker -- `make dev`'s MPS support relies
on the platform's default (non-CUDA) wheel, which this doesn't touch.

## Working without API keys

`USE_MOCK_PROVIDERS=true` (the default in `.env.example`) replaces Scopus and both
LLM tiers with deterministic offline stand-ins, so the entire pipeline runs with no
credentials. The mock Scopus serves fixture payloads through the *real* response
parser, and the mock LLM derives its answers from the same rule prefilter and
lexical overlap the pipeline uses, so results are reproducible and assertable.

Set `USE_MOCK_PROVIDERS=false` to use the real services. Startup then fails fast
with a clear message if any required key is missing, rather than quietly running on
mocks. You can also mock one side only with `MOCK_LLM` / `MOCK_SCOPUS`.

To get real keys:

| Key | Required? | Where |
|---|---|---|
| `ELSEVIER_API_KEY` | for real enrichment | https://dev.elsevier.com — register an app; institutional network or `ELSEVIER_INST_TOKEN` is needed for abstract entitlement |
| `DEEPSEEK_API_KEY` | **yes** | https://platform.deepseek.com/api_keys |
| `GEMINI_API_KEY` | optional | https://aistudio.google.com/apikey |

**Only one LLM key is needed, and it must be DeepSeek.** DeepSeek (`deepseek-chat`)
serves both tiers — claim classification and verification. Gemini 2.5 Flash is a
fallback for *both* tiers, but cannot substitute for DeepSeek as primary — without a
DeepSeek key, claim detection has no classifier.

Adding `GEMINI_API_KEY` is still worthwhile: if DeepSeek rate-limits or returns
unparseable JSON, the request retries against Gemini instead of degrading that
call to the `SKIPPED` verdict (verification) or failing the run (classification).

Originally built against Groq; switched to DeepSeek because Groq's free-tier
*token*-per-minute ceiling — not request volume, which had headroom the whole
time — was the real bottleneck on real papers, forcing repeated 45-60s stalls.
DeepSeek's API is OpenAI-compatible, so the swap was a config change, not a rewrite.

### Scopus abstract entitlement

A plain Elsevier developer key can read the Abstract Retrieval endpoint's *default*
view only. The `FULL` and `META_ABS` views — the ones that carry abstracts, author
lists, and keywords — return `AUTHORIZATION_ERROR` without an institutional
subscription, which normally means being on the university network or holding an
`ELSEVIER_INST_TOKEN` from your library.

The client handles this rather than failing: it downgrades to the entitled view and
keeps what that returns (title, year, source, EID, citation counts), then
**Semantic Scholar supplies the abstract** through the fallback chain. Semantic
Scholar needs no key and covers most recent literature, though not everything — a
paper neither source can supply an abstract for stays `INCOMPLETE`, is excluded
from retrieval, and is never proposed as evidence.

If you can obtain an `ELSEVIER_INST_TOKEN`, set it: Scopus abstracts come with
author and index keywords that improve the keyword-overlap component of the score.

## Verifying it works

```bash
make test      # 255 backend tests, no network and no model downloads
make smoke     # full pipeline on fixtures with the REAL SPECTER2 + cross-encoder
```

```bash
cd frontend && npm test   # 22 tests for the pure review-screen logic
cd frontend && npm run build
```

`make test` substitutes deterministic fake vectors for the local models so CI stays
fast and offline; absolute scores are therefore lower than production. `make smoke`
is the check that the retrieval stack behaves on your machine — on the fixture data
the planted supporting reference scores 93.4% SUPPORTED, and the planted
contradicting reference is capped at 20%. The frontend tests cover `buildSegments`
(the read-only draft renderer) and `highlightFor` (the six-colour priority logic) —
the two pure functions the whole review screen rests on.

## API

```
POST   /api/v1/projects
POST   /api/v1/projects/{id}/drafts/upload          multipart .docx/.md/.txt
POST   /api/v1/projects/{id}/references/import      multipart .xlsx/.csv
GET    /api/v1/projects/{id}/references/status
POST   /api/v1/projects/{id}/analysis/run
GET    /api/v1/projects/{id}/analysis/status
GET    /api/v1/drafts/{id}/claims?needs_citation=true
GET    /api/v1/claims/{id}/recommendations?limit=5
POST   /api/v1/recommendations/{id}/accept
POST   /api/v1/recommendations/{id}/reject
POST   /api/v1/projects/{id}/exports                {format, citation_style, insertion_mode, include_audit_report}
GET    /api/v1/projects/{id}/exports
GET    /api/v1/exports/{id}/download
```

### Export

`format` is one of `docx`, `md`, `csv`, `json`. DOCX inserts accepted citations
directly into the source paragraphs — by default as Word tracked changes
(`insertion_mode: tracked_changes`, the reviewable default; `direct` writes
plain text; `placeholder` writes `[CITATION: ...]` markers) — preserving run
formatting via oxml manipulation rather than `paragraph.text = ...`, which
would destroy it. A generated APA reference list is appended, and
`include_audit_report` (default `true`) appends a table covering every claim
that needed a citation: section, type, existing-citation status, score,
verdict, decision, and status.

Markdown export works for any draft format (.docx/.md/.txt) and is what a
`.docx`-only feature falls back to; requesting `docx` for a non-`.docx` draft
returns 422. CSV and JSON *are* the audit report rather than a document with
one appended.

If a claim's stored sentence no longer matches the live draft text (the file
was edited outside the tool since analysis), that citation is skipped and
reported as `POSITION_MISMATCH` in the response's `outcomes` and in the audit
report — never guessed. The export response includes `inserted_count` and
`mismatch_count` so the UI can warn before the user opens the file.

Export runs synchronously (not a Celery job): generating even a long document
takes tens of milliseconds, and queuing it behind a multi-minute analysis run
would feel broken for no benefit.

## Dataset format

Required columns: `DOCUMENT TITLE` and `LINK`. Optional: `NO.`, `YEAR`,
`FIELD OF STUDY`, `AUTHORS`, `SOURCE TITLE`, `DOI`, `EID`, `ABSTRACT`,
`AUTHOR KEYWORDS`, `INDEX KEYWORDS`, `CITATION COUNT`, `DOCUMENT TYPE`.

Headers are matched case-insensitively against an alias table, so `TITLE`/`URL`/
`JOURNAL` work as well as the canonical spellings. `LINK` may be a Scopus URL, a
doi.org URL, a bare DOI, a publisher landing page, or a Semantic Scholar URL —
identifiers are extracted from whichever form is present.

## Design notes

**`reference_papers`, not `references`.** `REFERENCES` is a reserved SQL word; the
rename avoids quoting it in every query.

**Scores are recommendations, not proof.** The verdict layer overrides similarity:
a contradicting paper is capped at 20%, a paper with no retrievable abstract at
45%, and a paper the verifier found no support in is never labeled "Recommended"
however similar it looks. When verification cannot run at all, the verdict is
`SKIPPED` and its weight is redistributed rather than scored as zero support.

**Char offsets.** Every claim's `char_start`/`char_end` indexes into
`drafts.raw_text`, which is assembled exactly once with normalization applied
before offsets are assigned. `raw_text[start:end] == sentence_text` is asserted in
the test suite for every block and sentence of every fixture — the export stage
(phase 6) depends on it to insert citations at the right position.

**SPECTER2 needs its adapter.** Loading `allenai/specter2_base` alone gives you the
base encoder without the proximity adapter that makes it good at retrieval. The
embedding service loads the adapter and verifies it actually activated, because
`load_adapter(set_active=True)` does not reliably route the forward pass on its own.

## Layout

```
app/
  api/routes/     projects, drafts, references, analysis, claims,
                  recommendations, exports
  core/           config, device (MPS/CUDA/CPU), logging, security, uploads
  db/             session (async for API, sync for workers), models
  services/       import, enrichment, embedding, retrieval, reranking,
                  verification, scoring, recommendation pipeline, mocks,
                  citation_formatting_service, export/ (bundle, docx_ops,
                  docx_writer, markdown_writer, tabular_writer, audit)
  workers/        celery app and the five pipeline stage tasks
scripts/          make_fixtures.py, warmup_models.py, smoke_pipeline.py
tests/            unit (no DB) and integration (compose test database)

frontend/
  app/            projects list; projects/[projectId]/{dashboard,setup,
                  review,export} pages, all client components
  components/     ui/ primitives, review/ (DraftPane, RecommendationCard,
                  ScoreBreakdownDrawer)
  lib/            api/ (generated schema + typed client + query hooks),
                  review/ (segments.ts, highlight.ts — the pure logic
                  the review screen is built on; both have Vitest suites)
```
