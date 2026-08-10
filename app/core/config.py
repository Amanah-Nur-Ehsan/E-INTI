from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database / broker
    database_url: str = "postgresql+asyncpg://dev:dev@localhost:5432/citation_db"
    sync_database_url: str = ""
    test_database_url: str = "postgresql+asyncpg://dev:dev@localhost:5432/citation_test"
    redis_url: str = "redis://localhost:6379/0"

    # External API keys
    elsevier_api_key: str = ""
    elsevier_inst_token: str = ""
    deepseek_api_key: str = ""
    gemini_api_key: str = ""

    # OpenAlex/Crossref "polite pool" contact email -- a real, monitored
    # address gets a meaningfully higher rate limit than an anonymous or
    # obviously-placeholder one (the shipped default uses the IANA-reserved
    # example.org domain specifically so it's never mistaken for a real
    # inbox, but that's also indistinguishable from spam/placeholder traffic
    # to OpenAlex's abuse detection -- a real deploy should override this).
    enrichment_contact_email: str = "citationinti@example.org"

    # Provider mocking
    use_mock_providers: bool = True
    mock_llm: bool | None = None
    mock_scopus: bool | None = None

    # Local models
    embedding_model: str = "allenai/specter2_base"
    embedding_adapter: str = "allenai/specter2"
    embedding_use_adapter: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    spacy_model: str = "en_core_web_sm"
    force_cpu: bool = False
    embedding_fake: bool = False
    reranker_fake: bool = False

    # LLM routing. DeepSeek is OpenAI-API-compatible, so the same client
    # code that used to talk to Groq talks to DeepSeek by swapping base_url
    # + key + model names. deepseek-chat (not deepseek-reasoner) for both
    # tiers: the reasoner model emits long chain-of-thought before its
    # answer, which is real latency for a "cheap, high-volume" classify
    # call and unnecessary for verification, which is a bounded judgment
    # call over a short abstract, not an open-ended reasoning problem.
    deepseek_base_url: str = "https://api.deepseek.com"
    tier1_model: str = "deepseek-chat"
    tier2_model: str = "deepseek-chat"
    gemini_fallback_model: str = "gemini-2.5-flash"

    # LLM pacing and rate limiting. Unlike Groq's free tier, DeepSeek does
    # not enforce a hard per-minute token ceiling -- the real bottleneck
    # this project hit was never request volume (Groq's RPM had headroom
    # the whole time), it was Groq's *token*-per-minute cap. This is a
    # *global* floor on the gap between call starts, shared by every thread
    # in the process, so 1/floor is the hard req/s ceiling for the whole
    # worker: at the old 0.3 it capped everything at 3.3 req/s and would
    # have throttled llm_max_concurrency to near-nothing.
    llm_min_seconds_between_requests: float = 0.1
    llm_max_attempts: int = 5
    llm_retry_base_seconds: float = 2.0
    llm_max_backoff_seconds: float = 60.0
    llm_timeout_seconds: float = 60.0
    #: In-flight LLM calls per analysis. The stages that use it (Tier-1
    #: batches, Tier-2 per-claim verification) are independent of each
    #: other, so the only reason they were ever serial was that nothing
    #: ran them concurrently. Worst case in flight across the worker is
    #: celery_concurrency * this; these are network waits, not CPU, so
    #: they cost nothing against the CPU budget below.
    llm_max_concurrency: int = 10
    #: Tier-2 verification calls per claim (was: all 10 reranked candidates).
    verify_limit: int = 3
    #: Sentences per Tier-1 classification call. Larger batches mean fewer
    #: round trips for the same work -- 25 turns a ~300-sentence paper's
    #: ~30 Tier-1 calls into ~12.
    classify_batch_size: int = 25
    #: The product now surfaces one ranked shortlist of references for the
    #: whole paper (see best_reference_* below), not a per-claim citation
    #: list -- so verifying every citation-worthy claim is mostly wasted
    #: Tier-2 spend. Only the claims whose best reranked candidate could
    #: plausibly place in that shortlist are worth an LLM call; the rest
    #: are cheap to skip since a paper's shortlist rarely needs more than a
    #: handful of well-matched claims to be found. On a 137-claim paper this
    #: is the difference between ~137 paced LLM calls and ~20.
    verify_claim_limit: int = 20
    #: How many claims enter *retrieval* at all (embedding + vector search
    #: + reranking), picked by Claim.claim_confidence descending. 0 = all.
    #:
    #: This is the single largest CPU saving in the pipeline. Retrieval used
    #: to run over every citation-worthy claim (~137 on a real paper:
    #: ~137 SPECTER2 embeddings and ~1,370 cross-encoder pairs) and only
    #: *then* keep the top verify_claim_limit -- so ~85% of the heaviest
    #: compute was produced and discarded. Capping here instead of after
    #: cuts that work ~3.4x, which is what makes a CPU-only server viable.
    #:
    #: Tradeoff, stated plainly: references are searched for among the N
    #: most confidently-citation-worthy claims rather than all of them. With
    #: only a handful of paper-level slots to fill that is very unlikely to
    #: change the result, but it *is* a behaviour change -- set 0 to restore
    #: the old exhaustive behaviour.
    retrieve_claim_limit: int = 40

    # Local-model CPU budget. torch defaults to using every core, which on
    # a shared box starves everything else -- these two settings together
    # are what bound it. torch_num_threads caps intra-op parallelism, and
    # device.local_inference()'s semaphore ensures only one analysis runs
    # torch at a time, so peak stays near one core regardless of how many
    # analyses are in flight. Raise torch_num_threads to trade CPU headroom
    # for faster embedding/reranking.
    torch_num_threads: int = 1
    #: Concurrent analyses. Informational for app code (the real value is
    #: --concurrency on the worker command line); kept here so the CPU
    #: budget above can be reasoned about in one place.
    celery_concurrency: int = 2

    # "Which single reference should this paper cite" thresholds. Below
    # min_score the match is too weak to present as usable; at or above
    # recommended_score it's shown as the preferred choice rather than
    # merely acceptable. The closest match is still returned below
    # min_score (flagged, never silently hidden) -- an empty result reads
    # as "broken," not "no reference is good enough yet."
    best_reference_min_score: float = 65.0
    best_reference_recommended_score: float = 75.0

    #: References older than this many years (inclusive of the current
    #: year) are never retrieved as candidates -- e.g. 5 in 2026 means only
    #: 2022-2026. A fixed institutional rule, not a per-run toggle; a
    #: reference with no year on file is treated as unverifiable recency
    #: and excluded the same as one that's too old.
    citation_recency_years: int = 5

    # Misc
    upload_dir: Path = Path("./uploads")
    celery_task_always_eager: bool = False
    max_upload_mb: int = 25
    cors_origins: list[str] = ["http://localhost:3000"]
    api_key: str = ""  # empty = auth disabled (local dev)

    @field_validator("mock_llm", "mock_scopus", mode="before")
    @classmethod
    def _empty_string_is_unset(cls, value: Any) -> Any:
        """`MOCK_LLM=` in .env means "not set" (inherit master flag), not a parse error."""
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("force_cpu", "embedding_fake", "reranker_fake", mode="before")
    @classmethod
    def _empty_string_is_false(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return False
        return value

    @property
    def llm_mocked(self) -> bool:
        return self.use_mock_providers if self.mock_llm is None else self.mock_llm

    @property
    def scopus_mocked(self) -> bool:
        return self.use_mock_providers if self.mock_scopus is None else self.mock_scopus

    @property
    def sync_db_url(self) -> str:
        if self.sync_database_url:
            return self.sync_database_url
        return self.database_url.replace("+asyncpg", "+psycopg")

    @model_validator(mode="after")
    def _fail_fast_on_missing_keys(self) -> "Settings":
        missing: list[str] = []
        if not self.scopus_mocked and not self.elsevier_api_key:
            missing.append("ELSEVIER_API_KEY")
        # DeepSeek serves both tiers, so it is the only mandatory LLM key.
        # Gemini is a fallback; without it a DeepSeek outage degrades
        # candidates to the SKIPPED verdict rather than failing the run.
        if not self.llm_mocked and not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if missing:
            raise ValueError(
                f"Real providers enabled but keys missing: {', '.join(missing)}. "
                "Set the keys in .env or set USE_MOCK_PROVIDERS=true."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
