# CitationINTI

Backend for a Scopus reference citation recommender. A researcher uploads a draft
paper and a spreadsheet of Scopus-indexed candidate references; the system finds the
sentences that make citable claims and recommends references **from that uploaded
dataset only**, each with a percentage score and an LLM-verified support verdict.

This repository currently covers phases 1–4 of the plan: infrastructure, dataset
import and enrichment, draft parsing and claim detection, and the recommendation
engine. The frontend and the DOCX export with tracked changes are not built yet.

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

## Running

```bash
make api       # FastAPI on http://localhost:8000 (docs at /docs)
make worker    # Celery worker — run this on the host, not in Docker
```

The worker must run on the host: Docker Desktop cannot reach the Apple Silicon
GPU, so a containerised worker silently falls back to CPU and runs several times
slower. It uses `--pool=solo` because forking a process that has already
initialised MPS is crash-prone.

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

| Key | Where |
|---|---|
| `ELSEVIER_API_KEY` | https://dev.elsevier.com — register an app; institutional network or `ELSEVIER_INST_TOKEN` is needed for abstract entitlement |
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

## Verifying it works

```bash
make test      # 133 tests, no network and no model downloads
make smoke     # full pipeline on fixtures with the REAL SPECTER2 + cross-encoder
```

`make test` substitutes deterministic fake vectors for the local models so CI stays
fast and offline; absolute scores are therefore lower than production. `make smoke`
is the check that the retrieval stack behaves on your machine — on the fixture data
the planted supporting reference scores 93.4% SUPPORTED, and the planted
contradicting reference is capped at 20%.

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
```

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
  api/routes/     projects, drafts, references, analysis, claims, recommendations
  core/           config, device (MPS/CUDA/CPU), logging
  db/             session (async for API, sync for workers), models
  services/       import, enrichment, embedding, retrieval, reranking,
                  verification, scoring, recommendation pipeline, mocks
  workers/        celery app and the five pipeline stage tasks
scripts/          make_fixtures.py, warmup_models.py, smoke_pipeline.py
tests/            unit (no DB) and integration (compose test database)
```
