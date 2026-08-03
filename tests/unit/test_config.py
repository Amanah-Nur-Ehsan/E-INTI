import pytest

from app.core.config import Settings


def real_providers(**overrides) -> dict:
    base = {
        "use_mock_providers": False,
        "elsevier_api_key": "els-key",
        "deepseek_api_key": "deepseek-key",
        "gemini_api_key": "gemini-key",
        "_env_file": None,
    }
    base.update(overrides)
    return base


def test_deepseek_alone_is_sufficient():
    """DeepSeek serves both tiers; Gemini only backstops verification."""
    settings = Settings(**real_providers(gemini_api_key=""))
    assert settings.llm_mocked is False


def test_missing_deepseek_fails_fast():
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        Settings(**real_providers(deepseek_api_key=""))


def test_missing_scopus_key_fails_fast():
    with pytest.raises(ValueError, match="ELSEVIER_API_KEY"):
        Settings(**real_providers(elsevier_api_key=""))


def test_mocking_one_provider_only_requires_the_other_key():
    settings = Settings(
        **real_providers(mock_scopus=True, elsevier_api_key="", gemini_api_key="")
    )
    assert settings.scopus_mocked is True
    assert settings.llm_mocked is False


def test_mock_flags_inherit_the_master_switch():
    settings = Settings(use_mock_providers=True, _env_file=None)
    assert settings.llm_mocked and settings.scopus_mocked

    override = Settings(
        use_mock_providers=True, mock_scopus=False, elsevier_api_key="k", _env_file=None
    )
    assert override.llm_mocked and not override.scopus_mocked


def test_sync_url_is_derived_from_the_async_url():
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost:5433/db", _env_file=None
    )
    assert settings.sync_db_url == "postgresql+psycopg://u:p@localhost:5433/db"
