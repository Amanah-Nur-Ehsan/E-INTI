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
    groq_api_key: str = ""
    gemini_api_key: str = ""

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

    # LLM routing
    groq_base_url: str = "https://api.groq.com/openai/v1"
    tier1_model: str = "llama-3.1-8b-instant"
    tier2_model: str = "llama-3.3-70b-versatile"
    gemini_fallback_model: str = "gemini-2.5-flash"

    # Misc
    upload_dir: Path = Path("./uploads")
    celery_task_always_eager: bool = False

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
        if not self.llm_mocked:
            if not self.groq_api_key:
                missing.append("GROQ_API_KEY")
            if not self.gemini_api_key:
                missing.append("GEMINI_API_KEY")
        if missing:
            raise ValueError(
                f"Real providers enabled but keys missing: {', '.join(missing)}. "
                "Set the keys in .env or set USE_MOCK_PROVIDERS=true."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
