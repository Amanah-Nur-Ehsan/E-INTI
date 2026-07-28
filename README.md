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
make api       # FastAPI on http://localhost:8000 (docs at /docs)
make worker    # Celery worker — run this on the host, not in Docker
```

The worker must run on the host: Docker Desktop cannot reach the Apple Silicon
GPU, so a containerised worker silently falls back to CPU and runs several times
slower. It uses `--pool=solo` because forking a process that has already
initialised MPS is crash-prone.

```bash
make web       # Next.js on http://localhost:3000, proxying /api/* to the backend
```

The frontend is a separate `npm` project in `frontend/` — no Docker container for
it, since the API and worker already run on the host for MPS and a Node container
would just add a container-to-host networking hop for nothing. Its typed API client
is generated from the running backend's OpenAPI schema (`lib/api/schema.d.ts`,
checked into git) via `make gen-api`; regenerate it whenever the API shape changes.

The review screen renders the draft **read-only** — the user accepts or rejects
suggestions, they never edit prose. A rich-text editor was deliberately not used:
`char_start`/`char_end` offsets are not meaningful inside a ProseMirror/Lexical
document model, and the moment the user could type, every stored offset would go
stale and silently fail export's `POSITION_MISMATCH` check. Highlights and ghost
text are computed by two pure functions (`lib/review/segments.ts`,
`lib/review/highlight.ts`) over plain `raw_text` and the claim list instead.

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
| `GROQ_API_KEY` | **yes** | https://console.groq.com/keys |
| `GEMINI_API_KEY` | optional | https://aistudio.google.com/apikey |

**Only one LLM key is needed, and it must be Groq.** Groq serves both tiers:
`llama-3.1-8b-instant` for claim classification and `llama-3.3-70b-versatile` for
verification. Gemini 2.5 Flash is a fallback for the verification tier alone, so it
cannot substitute for Groq — without a Groq key, claim detection has no classifier.

Adding `GEMINI_API_KEY` is still worthwhile: if Groq rate-limits or returns
unparseable JSON during verification, the request retries against Gemini instead of
degrading those candidates to the `SKIPPED` verdict.

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
